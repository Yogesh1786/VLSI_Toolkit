* 3-stage CMOS inverter chain - runs in plain ngspice (simple level-1 models, no PDK needed)
.param VDD=1.8 WN=0.42u WP=0.84u LMIN=0.15u CL=10f

.model nch nmos (level=1 vto=0.45  kp=220u lambda=0.05 cgso=0.3n cgdo=0.3n cox=8m)
.model pch pmos (level=1 vto=-0.45 kp=80u  lambda=0.05 cgso=0.3n cgdo=0.3n cox=8m)

.subckt inv in out vdd vss
M1 out in vdd vdd pch W={WP} L={LMIN}
M2 out in vss vss nch W={WN} L={LMIN}
.ends inv

Vsup vdd 0 {VDD}
Vin  in  0 PULSE(0 {VDD} 0.2n 50p 50p 1n 2n)

X1 in n1  vdd 0 inv
X2 n1 n2  vdd 0 inv
X3 n2 out vdd 0 inv
Cload out 0 {CL}

.tran 1p 6n
* output inverts the input (3 stages): measure on the 2nd input edges
.meas tran tphl TRIG v(in) VAL='VDD/2' RISE=2 TARG v(out) VAL='VDD/2' FALL=2
.meas tran tplh TRIG v(in) VAL='VDD/2' FALL=2 TARG v(out) VAL='VDD/2' RISE=2
.meas tran trise TRIG v(out) VAL='0.1*VDD' RISE=2 TARG v(out) VAL='0.9*VDD' RISE=2
.control
run
wrdata inverter_tran.txt v(in) v(out)
.endc
.end
