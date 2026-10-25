// Steel cantilever 100 x 10 x 5 mm, clamped at y = 0, 50 N on the free end (-z).
// Beam theory: deflection F L^3 / (3 E I) = 50 * 100^3 / (3 * 200000 * 10*5^3/12) = 0.80 mm
//   max stress 6 F L / (b h^2) = 6 * 50 * 100 / (10 * 25) = 120 MPa

beam_len = 100;

//@sim material=pla
module beam() color("gray") translate([-5, 0, 0]) cube([10, beam_len, 5]);

//@sim fixed
module wall() color("green") translate([-6, -1, -1]) cube([12, 1.1, 7]);

//@sim load force=[0,0,50]
module tip() color("red") translate([-6, beam_len-0.1, -1]) cube([12, 1.1, 7]);

beam();
%wall();
%tip();
