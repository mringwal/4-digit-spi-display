from amaranth import *
from amaranth.sim import Simulator
from amaranth.back import rtlil, verilog
from amaranth.lib import stream, wiring
from amaranth.lib.wiring import In, Out

class SPI_Out(wiring.Component):
    en:      In(1)
    spi_out: Out(1)
    spi_clk: Out(1)
    spi_ss:  Out(1)
    stream:  In(stream.Signature(8))

    prescale_counter = Signal(8)

    def __init__(self, prescaler = 1):
        super().__init__()
        self.count = Signal(range(9))
        self.data = Signal(8)
        self.prescaler = prescaler

    def elaborate(self, platform) -> Module:
        m = Module()
        m.d.comb += self.spi_ss.eq(self.en)
        with m.If(~self.en):
            m.d.sync += self.count.eq(0)
            m.d.sync += self.spi_clk.eq(0)
            m.d.sync += self.spi_out.eq(0)
            m.d.sync += self.prescale_counter.eq(self.prescaler)
        with m.Elif(self.count == 0):
            m.d.sync += self.stream.ready.eq(1)
            with m.If(self.stream.valid):
                m.d.sync += self.data.eq(self.stream.payload)
                m.d.sync += self.count.eq(8)
        with m.Else():
            m.d.sync += self.stream.ready.eq(0)
            with m.If(self.prescale_counter > 0):
                m.d.sync += self.prescale_counter.eq(self.prescale_counter - 1)
            with m.Else():
                m.d.sync += self.prescale_counter.eq(self.prescaler)
                m.d.sync += self.spi_clk.eq(~self.spi_clk)
                with m.If(self.spi_clk):
                    m.d.sync += self.data.eq(self.data << 1)
                    m.d.sync += self.spi_out.eq(self.data[-1])
                with m.Else():
                    m.d.sync += self.count.eq(self.count - 1)
        return m


async def stream_put(ctx, stream, payload):
    ctx.set(stream.payload, payload)
    ctx.set(stream.valid, 1)
    await ctx.tick().until(stream.ready)
    ctx.set(stream.valid, 0)


async def testbench_input(ctx):
    for _ in range(5):
        await ctx.tick()

    ctx.set(dut.en, 1)
    await stream_put(ctx, dut.stream, 0xaa)
    await stream_put(ctx, dut.stream, 0xcc)
    await ctx.tick().until(dut.stream.ready) 

    for _ in range(5):
        await ctx.tick()
    ctx.set(dut.en, 0)


if __name__ == "__main__":

    dut = SPI_Out()

    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_testbench(testbench_input)

    with sim.write_vcd("spi_out.vcd"):
        sim.run()
