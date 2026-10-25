// Two PLA blocks butted at y = 0, joined by a steel bar bonded in a slot cut in both.
// The far end of the right block is clamped, the far end of the left one is pulled sideways:
// the bar carries the bending.

//@sim contact left right mode=frictionless
module bar() translate([-4, -30, -4]) cube([8, 60, 8]);

//@sim material=pla
module left() difference() {
    translate([-20, -60, -10]) cube([40, 60, 20]);
    bar();
}

//@sim material=pla
module right() difference() {
    translate([-20, 0, -10]) cube([40, 60, 20]);
    bar();
}

//@sim material=steel h=3
module steel_bar() bar();

//@sim fixed
module clamp() translate([-21, 59, -11]) cube([42, 2, 22]);

//@sim load force=[200,0,0]
module pull() translate([-21, -61, -11]) cube([42, 2, 22]);

left();
right();
steel_bar();
