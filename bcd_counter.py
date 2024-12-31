from amaranth import *
from amaranth.sim import Simulator
from amaranth.back import rtlil, verilog
from amaranth.lib import data, wiring
from amaranth.lib.wiring import In, Out

bcd_counter = data.ArrayLayout(unsigned(4), 4)

class BCD_Counter(wiring.Component):

    en: In(1)
    counter: Out(bcd_counter)
    
    def elaborate(self, platform) -> Module:
        m = Module()

        print(self.counter)

        with m.If(~self.en):
            for i in range(4):
                self.counter[i].eq(0)
        with m.Elif(self.counter[0] < 9):
            m.d.sync += self.counter[0].eq(self.counter[0] + 1)
        with m.Else():
            m.d.sync += self.counter[0].eq(0)
            with m.If(self.counter[1] < 9):
                m.d.sync += self.counter[1].eq(self.counter[1] + 1)
            with m.Else():
                m.d.sync += self.counter[1].eq(0)
                with m.If(self.counter[2] < 9):
                    m.d.sync += self.counter[2].eq(self.counter[2] + 1)
                with m.Else():
                    m.d.sync += self.counter[2].eq(0)
                    with m.If(self.counter[3] < 9):
                        m.d.sync += self.counter[3].eq(self.counter[3] + 1)
                    with m.Else():
                        m.d.sync += self.counter[3].eq(0)
        return m


if __name__ == "__main__":

    def get_value(ctx):
        value = 0
        for j in range(4):
            value *= 10
            value += ctx.get(dut.counter[3-j])
        return value 

    async def tesbench_bcd_counter(ctx):
        # disable counter
        ctx.set(dut.en, 0)
        for _ in range(3):
            assert get_value(ctx) == 0
            await ctx.tick()

        # enable counter
        ctx.set(dut.en, 1)
        for i in range(111):
            assert get_value(ctx) == i
            await ctx.tick()

    dut = BCD_Counter()

    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_testbench(tesbench_bcd_counter)

    with sim.write_vcd("bcd_counter.vcd"):
        sim.run()
