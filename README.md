# 4-Digit Counter with MAX7219 8x8 Display

A modern example of the classic 7-segment counter using a 4-digit 8x8 LED display with an SPI MAX7219 interface using Amaranth.

## BCD Counter

Instead of counting in binary and then converting it to BCD, using e.g. the interesting [double dabble](https://en.wikipedia.org/wiki/Double_dabble) algorithm, it seemed easier to directly count in BCD.

## Font

Minimal component that contains a 8x8 pixel font with the default data stream interface.

## Thing
Main statemachine to initialize the SPI display which triggers the counter and updates the display.

A statemachine is used to:
- init display
- wait for next counter tick
- update display by sending one row at a time. The conversion between character and bitmap is done on the fly
