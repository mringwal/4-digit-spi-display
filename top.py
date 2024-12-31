from amaranth import *
from amaranth.sim import Simulator
from amaranth.back import rtlil, verilog
from amaranth.lib import stream, wiring
from amaranth.lib.wiring import In, Out
from bcd_counter import BCD_Counter, bcd_counter
from font import Font, font_request

class Thing(wiring.Component):

    clock   = Signal(32)

    refresh = Signal(1)
    digit   = Signal(2)
    counter = Array([Signal(4) for _ in range(4)])

    i_stream: In(stream.Signature (unsigned(8)))
    o_stream: Out(stream.Signature(unsigned(8)))
    spi_ss:   Out(1)

    def elaborate(self, platform) -> Module:
        if platform is not None:
            half_freq = int(platform.default_clk_frequency // 2)
        else:
            half_freq = 200

        m = Module()
        m.submodules.bcd_counter = bcd_counter = BCD_Counter()
        m.submodules.font        = font        = Font()

        # connect to font module
        wiring.connect(m, out_stream = font.o_stream, in_stream = self.i_stream)

        # TODO: connect font module to SPI_out

        # counter
        with m.If(self.clock == half_freq):
            m.d.sync += bcd_counter.en.eq(1)
            m.d.sync += self.clock.eq(0)
            m.d.sync += self.refresh.eq(1)
        with m.Else():
            m.d.sync += bcd_counter.en.eq(0)
            m.d.sync += self.clock.eq(self.clock + 1)

        with m.FSM():
            with m.State("Init"):
                # TODO reset everything
                # TODO configure display
                m.d.sync += self.refresh.eq(1)
                m.next = "Tick"
            with m.State("Tick"):
                with m.If(self.refresh):
                    m.d.sync += [
                        self.digit.eq(3),
                        font.i_stream.payload.row.eq(0),
                    ]
                    # cache counter
                    for i in range(4):
                        m.d.sync += self.counter[i].eq(bcd_counter.counter[i])
                    m.next = "GetRow"
            with m.State("GetRow"):
                m.d.sync += [
                    # provide input to font module
                    font.i_stream.payload.character.eq(self.counter[self.digit] + 0x030),
                    font.i_stream.valid.eq(1),
                    # we are ready to receive bitmap
                    self.i_stream.ready.eq(1),
                    # row active
                    self.spi_ss.eq(1) 
                ]
                m.next = "WaitForRow"
            with m.State("WaitForRow"):
                # when font modules provides bitmpap data
                with m.If(self.i_stream.valid):
                    # busy
                    m.d.sync += self.i_stream.ready.eq(0)
                    # no new request
                    m.d.sync += font.i_stream.valid.eq(0)
                    # cache bitmap
                    m.d.sync += self.o_stream.valid.eq(1)
                    m.d.sync += self.o_stream.payload.eq(self.i_stream.payload)
                    m.next = "SendRow"
            with m.State("SendRow"):
                with m.If(self.o_stream.ready):
                    m.d.sync += self.o_stream.valid.eq(0)
                    m.next = "RowSent"
            with m.State("RowSent"):
                m.next = "GetRow"
                with m.If(self.digit > 0):
                    m.d.sync += self.digit.eq(self.digit - 1)
                with m.Else():
                    m.d.sync += self.spi_ss.eq(0) 
                    m.d.sync += self.digit.eq(3)
                    with m.If(font.i_stream.payload.row < 7):
                        m.d.sync += font.i_stream.payload.row.eq(font.i_stream.payload.row + 1)
                    with m.Else():
                        m.next = "Tick"

        return m

async def stream_get(ctx, stream):
    ctx.set(stream.ready, 1)
    payload, = await ctx.tick().sample(stream.payload).until(stream.valid)
    ctx.set(stream.ready, 0)
    return payload


async def testbench(ctx):
        
    for _ in range(20):

        print("/" * 56)
        for _ in range(8):
            for _ in range(4):
                print("---", end="")
                value = await stream_get(ctx, dut.o_stream)
                for i in range(8):
                    if (value & 0x01) > 0:
                        print("x", end="")
                    else:
                        print(" ", end="")
                    value = value >> 1
                print("---", end="")
            print()
        print("\\" * 56)

    # wait for next 
    await ctx.tick().until(dut.refresh)

dut = Thing()

sim = Simulator(dut)
sim.add_clock(1e-6)
sim.add_testbench(testbench)

with sim.write_vcd("top.vcd"):
    sim.run()
