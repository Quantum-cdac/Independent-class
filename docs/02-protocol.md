# BB84 in plain words

1. **Alice sends random bits in random bases.** For each round she picks a bit
   (0 or 1) and a basis (Z or X) and prepares one qubit: `|0>`, `|1>`, `|+>`
   or `|->`.
2. **Bob measures in a random basis.** Half the time he guesses Alice's basis.
3. **Sifting.** Over a public channel they keep only the rounds where their
   bases matched. With no interference, those bits are identical.
4. **Eavesdropping leaves fingerprints.** Eve does not know the basis either.
   When she intercepts and resends in the wrong basis, she randomises the
   qubit, and about 25% of the sifted bits flip. Bob and Alice compare a
   sample: a high error rate (above 11%) reveals her.

## The threat model in this demo

Eve performs the classic **intercept-resend** attack: she measures every qubit
in a random basis and forwards the result. On real hardware her measurement
collapses the state. On a simulator we get the identical statistics coherently:
a CNOT couples Alice's qubit to Eve's ancilla in Eve's basis, so the same
information leak and the same disturbance appear with only final measurements
(no mid-circuit measurement or reset required, which keeps the circuit
portable across backends).

## Why 25%?

When Alice and Bob's bases match (the sifted rounds), Eve's basis agrees with
theirs only half the time. When it disagrees, Bob's outcome is randomised -
wrong half the time. Half of half is 25% average error on the sifted key.

## What the flag means - and what it does not

A high error rate is what eavesdropping looks like, but noise can produce one
too. The report therefore says "possible eavesdropping or channel noise" and
shows the configured scenario separately from what the detector can know. In
this simulation we control both, which is exactly what makes it a good
teaching tool.

## What this demo does not claim

Finite runs scatter around 25% (sampling error is reported next to every
number). The 11% flag is the textbook BB84 bound used for teaching, not a
security certification. Real QKD adds error correction, privacy amplification
and authenticated classical channels - out of scope here.
