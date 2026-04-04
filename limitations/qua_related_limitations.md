# QUA-Related Limitations

## Control-Program Conditional Acquire Lowering

**Date observed:** 2026-04-03
**Area:** `ControlProgram` → QM lowering

**Symptom:**

`AcquireInstruction` with a non-`None` condition is rejected during lowering.

**Reason:**

The current `CircuitCompiler` measurement path emits measurements unconditionally
and does not yet wrap measurement statements in a QUA branch structure for
control-program-native conditional acquisition.

**Workaround:**

- Gate the surrounding pulse or semantic gate sequence before the acquisition.
- Or lower to an unconditional acquire and apply the branch logic in analysis.

**Impact:**

`session.exp.custom(control=...)` supports conditional control operations, but
not conditional acquisition in the QM lowering path yet.