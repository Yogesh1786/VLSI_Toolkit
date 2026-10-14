* Current mirror with two deliberate connectivity bugs (for 'spice info' checks)
.param IREF=20u
.model nch nmos (level=1 vto=0.45 kp=220u)
Vdd vdd 0 1.8
Iref vdd nref {IREF}
M1 nref nref 0 0 nch W=2u L=0.5u
M2 nout nref 0 0 nch W=2u L=0.5u m=4
* BUG: bias_en drives a gate but nothing drives bias_en
M3 nout bias_en ntail 0 nch W=1u L=0.18u
* BUG: typo 'ntial' instead of 'ntail' leaves both nodes dangling
Rtail ntial 0 10k
Rload vdd nout 20k
.op
.end
