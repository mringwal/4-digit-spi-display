from amaranth import *
from amaranth.sim import Simulator
from amaranth.back import rtlil, verilog
from amaranth.lib import stream, wiring
from amaranth.lib.wiring import In, Out
from bcd_counter import BCD_Counter, bcd_counter
from font import Font, font_request
from spi_out import SPI_Out
import os

# constants
NUM_MODULES = 4
DISPLAY_HEIGHT = 8

DECODE_MODE_REG = 0x09
BRIGHTNESS_REG = 0x0A
SCAN_LIMIT_REG = 0x0B
SHUTDOWN_REG = 0x0C
DISPLAY_TEST_REG = 0x0F

init_display = [
    [SHUTDOWN_REG, 0x0],
    [DISPLAY_TEST_REG, 0x0],
    [SCAN_LIMIT_REG, 0x7],
    [DECODE_MODE_REG, 0x0],
    [SHUTDOWN_REG, 0x1],
    [BRIGHTNESS_REG, 0x2 & 0x0f],
] 

class Thing(Elaboratable):

    clock   = Signal(32)

    refresh = Signal(1)
    digit   = Signal(2)
    counter = Array([Signal(4) for _ in range(4)])
    step    = Signal(6)
    spi_active = Signal(1)

    # i_stream: In(stream.Signature (unsigned(8)))
    # o_stream: Out(stream.Signature(unsigned(8)))

    spi_valid      = Signal(1)
    spi_ready      = Signal(1)
    spi_payload    = Signal(8)

    bitmap_valid   = Signal(1)
    bitmap_ready   = Signal(1)
    bitmap_payload = Signal(8)

    def __init__(self, prescaler = 1):
        super().__init__()
        self.prescaler = prescaler
        self.prescale_counter = Signal(range(prescaler+1))


    def elaborate(self, platform) -> Module:
        if platform is not None:
            half_freq = int(platform.default_clk_frequency // 2)
            spi_ss   = platform.request("spi_ss").o
            spi_clk  = platform.request("spi_clk").o
            spi_data = platform.request("spi_data").o
            led      = platform.request("led").o
        else:
            half_freq = 1000
            spi_ss    = Signal(1)
            spi_clk   = Signal(1)
            spi_data  = Signal(1)
            led       = Signal(1)

        m = Module()
        m.submodules.bcd_counter = bcd_counter = BCD_Counter()
        m.submodules.font        = font        = Font()
        m.submodules.spi_out     = spi_out     = SPI_Out(self.prescaler)

        # connect to font module
        # wiring.connect(m, bitmap_producer = font.o_stream, bitmap_consumer = self.i_stream)
        m.d.comb += [
            self.bitmap_payload.eq(font.o_stream.payload),
            self.bitmap_valid.eq(font.o_stream.valid),
            font.o_stream.ready.eq(self.bitmap_ready),
        ]

        # connect to SPI Out
        # wiring.connect(m, display_producer = self.o_stream, display_consumer = spi_out.stream)
        m.d.comb += [
            spi_out.stream.valid.eq(self.spi_valid),
            spi_out.stream.payload.eq(self.spi_payload),
            self.spi_ready.eq(spi_out.stream.ready),
            spi_data.eq(spi_out.spi_out),
            spi_clk.eq(spi_out.spi_clk),
            # SS is active low
            spi_ss.eq(~spi_out.spi_ss),
        ]


        # counter
        with m.If(self.clock == half_freq):
            m.d.sync += bcd_counter.en.eq(1)
            m.d.sync += self.clock.eq(0)
            m.d.sync += self.refresh.eq(1)
            m.d.sync += led.eq(~led)
        with m.Else():
            m.d.sync += bcd_counter.en.eq(0)
            m.d.sync += self.clock.eq(self.clock + 1)

        with m.FSM():
            with m.State("Init"):
                m.d.sync += [
                    self.refresh.eq(1),
                    self.step.eq(0),
                    self.digit.eq(NUM_MODULES - 1),
                    self.prescale_counter.eq(self.prescaler),
                ]
                m.next = "Config_SendReg"

            with m.State("Config_SendReg"):
                m.d.sync += spi_out.en.eq(1) 
                for i in range(len(init_display)):
                    reg, _ = init_display[i]
                    with m.If(self.step == i):
                        m.d.sync += self.spi_payload.eq(reg)
                m.d.sync += self.spi_valid.eq(1)
                with m.If(self.spi_ready):
                    m.next = "Config_W4SendRegActive"

            with m.State("Config_W4SendRegActive"):
                m.d.sync += self.spi_valid.eq(0)
                with m.If(~self.spi_ready):
                    m.next = "Config_W4SendRegComplete"

            with m.State("Config_W4SendRegComplete"):
                with m.If(self.spi_ready):
                    m.next = "Config_SendValue"

            with m.State("Config_SendValue"):
                for i in range(len(init_display)):
                    _, value = init_display[i]
                    with m.If(self.step == i):
                        m.d.sync += self.spi_payload.eq(value)
                m.d.sync += self.spi_valid.eq(1)
                with m.If(self.spi_ready):
                    m.next = "Config_W4SendValueActive"

            with m.State("Config_W4SendValueActive"):
                m.d.sync += self.spi_valid.eq(0)
                with m.If(~self.spi_ready):
                    m.next = "Config_W4SendValueComplete"

            with m.State("Config_W4SendValueComplete"):
                with m.If(self.spi_ready):
                    m.next = "Config_Next"

            with m.State("Config_Next"):
                with m.If(self.digit > 0):
                    m.d.sync += self.digit.eq(self.digit - 1)
                    m.next = "Config_SendReg"
                with m.Else():
                    m.d.sync += spi_out.en.eq(0) 
                    with m.If(self.prescale_counter > 0):
                        m.d.sync += self.prescale_counter.eq(self.prescale_counter - 1)
                    with m.Else():
                        m.d.sync += self.prescale_counter.eq(self.prescaler)
                        m.d.sync += self.digit.eq(NUM_MODULES - 1)
                        with m.If(self.step < (len(init_display) - 1)):
                            m.d.sync += self.step.eq(self.step + 1)
                            m.next = "Config_SendReg"
                        with m.Else():
                            m.next = "Tick"

            with m.State("Tick"):
                with m.If(self.refresh):
                    m.d.sync += [
                        self.digit.eq(NUM_MODULES - 1),
                        font.i_stream.payload.row.eq(0),
                    ]
                    # cache counter
                    for i in range(4):
                        m.d.sync += self.counter[i].eq(bcd_counter.counter[i])
                    m.next = "SendUpdate"

            with m.State("SendUpdate"):
                m.d.sync += spi_out.en.eq(1) 
                with m.If(~self.spi_valid):
                    m.d.sync += [
                        self.spi_valid.eq(1),
                        self.spi_payload.eq(font.i_stream.payload.row + 1)
                    ]
                with m.Elif(self.spi_ready):
                    m.d.sync += self.spi_valid.eq(0)
                    m.next = "GetRow"

            with m.State("GetRow"):
                m.d.sync += [
                    # provide input to font module
                    font.i_stream.payload.character.eq(self.counter[self.digit] + 0x030),
                    font.i_stream.valid.eq(1),
                    # we are ready to receive bitmap
                    self.bitmap_ready.eq(1),
                    # row active
                    spi_out.en.eq(1) 
                ]
                m.next = "WaitForRow"

            with m.State("WaitForRow"):
                # when font modules provides bitmpap data
                with m.If(self.bitmap_valid):
                    # busy
                    m.d.sync += self.bitmap_ready.eq(0)
                    # no new request
                    m.d.sync += font.i_stream.valid.eq(0)
                    # cache bitmap
                    m.d.sync += self.spi_valid.eq(1)
                    m.d.sync += self.spi_payload.eq(self.bitmap_payload)
                    m.next = "SendRow"

            with m.State("SendRow"):
                with m.If(self.spi_ready):
                    m.d.sync += self.spi_valid.eq(0)
                    m.next = "RowSent"
                    
            with m.State("RowSent"):
                with m.If(self.digit > 0):
                    m.d.sync += self.digit.eq(self.digit - 1)
                    m.next = "SendUpdate"
                with m.Else():
                    m.d.sync += spi_out.en.eq(0) 
                    with m.If(self.prescale_counter > 0):
                        m.d.sync += self.prescale_counter.eq(self.prescale_counter - 1)
                    with m.Else():
                        m.d.sync += self.prescale_counter.eq(self.prescaler)
                        m.d.sync += self.digit.eq(3)
                        with m.If(font.i_stream.payload.row < 7):
                            m.d.sync += font.i_stream.payload.row.eq(font.i_stream.payload.row + 1)
                            m.next = "SendUpdate"
                        with m.Else():
                            m.next = "Tick"

        return m


async def stream_get(ctx, stream):
    ctx.set(stream.ready, 1)
    payload, = await ctx.tick().sample(stream.payload).until(stream.valid)
    ctx.set(stream.ready, 0)
    return payload


async def stream_peek(ctx, stream_payload, stream_ready, stream_valid):
    payload, = await ctx.tick().sample(stream_payload).until(stream_valid & stream_ready)
    return payload


async def testbench(ctx):

    # verify init sequence
    for [expected_reg, expected_value] in init_display:
        for _ in range(NUM_MODULES):
            actual_reg   = await stream_peek(ctx, dut.spi_payload, dut.spi_ready, dut.spi_valid)
            actual_value = await stream_peek(ctx, dut.spi_payload, dut.spi_ready, dut.spi_valid)
            print(f"expected {expected_reg:02x} = {expected_value:02x} //  actual {actual_reg:02x} = {actual_value:02x}")
            assert actual_reg   == expected_reg
            assert actual_value == expected_value

    for _ in range(10):
        print("/" * 56)
        for i in range(8):
            for _ in range(4):
                print("---", end="")
                actual_reg   = await stream_peek(ctx, dut.spi_payload, dut.spi_ready, dut.spi_valid)
                expected_reg = i + 1
                if actual_reg != expected_reg:
                    print(f"expected {expected_reg:02x}, actual {actual_reg:02x}")
                    assert False
                value = await stream_peek(ctx, dut.spi_payload, dut.spi_ready, dut.spi_valid)
                for _ in range(8):
                    if (value & 0x01) > 0:
                        print("x", end="")
                    else:
                        print(" ", end="")

                    value = value >> 1
                print("---", end="")
            print()
        print("\\" * 56)

        # wait for next tick
        await ctx.tick().until(dut.refresh)

dut = Thing(16)

sim = Simulator(dut)
sim.add_clock(1e-6)
sim.add_testbench(testbench)

with sim.write_vcd("top.vcd"):
    sim.run()

exit

# with open("top.v", "w") as f:
#     f.write(verilog.convert(dut))

from amaranth_boards.tinyfpga_bx import TinyFPGABXPlatform
from amaranth.build import Resource, Pins, Attrs

platform = TinyFPGABXPlatform()
# Add your custom pin resource if needed
platform.add_resources([
    Resource("spi_ss",   0, Pins("A2", dir="o"), Attrs(IO_STANDARD="SB_LVCMOS")),
    Resource("spi_clk",  0, Pins("A1", dir="o"), Attrs(IO_STANDARD="SB_LVCMOS")),
    Resource("spi_data", 0, Pins("B1", dir="o"), Attrs(IO_STANDARD="SB_LVCMOS"))
])
platform.build(dut, do_program=False)
