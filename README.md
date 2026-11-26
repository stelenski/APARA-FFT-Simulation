# APARA Radix-4 FFT Simulation

This repository contains an APARA MCode toolchain and a double-precision
(float64) Radix-4 FFT implementation. It provides the
assembler/simulator utilities, scripts to generate and execute FFT
programs for different transform lengths, and a summary of recorded
simulation results.

## 1. APARA and the FFT implementation

### APARA accelerator environment

APARA is the target accelerator environment used by this project. The
FFT is expressed in APARA MCode, an assembly-like instruction format
that is processed by the tools in `bin/`. The supplied toolchain aligns
the MCode, assembles it into an object file, can disassemble that
object, and runs the program in the simulator.

The MCode programs use instruction bundles with up to eight instruction
slots. This feature mirrors APARA accelerator's architecture. The FFT implementation takes advantage of this format through
software-pipelined loops, wide 256-bit loads/stores, and floating-point
operations. The repository includes the simulator/tool executables; it
does not include a hardware bitstream or a physical accelerator
configuration.

### Radix-4 FFT

The implementation is an **in-place, decimation-in-frequency (DIF),
radix-4 FFT** using complex float64 data.

A radix-4 butterfly combines four input values and produces four output
values. At each radix-4 stage, the transform length is reduced by a
factor of four:

N → N/4 → N/16 → ⋯

The stages use twiddle factors

$\[ W_N\^k = e\^{-j2`\pi `{=tex}k/N}. \]$
$W_N^k = e^{-j2\pi k/N}$

The implementation stores the first half of the twiddle table (`N/2`
complex values). It uses conjugate symmetry where required, and reuses
the twiddle-factor memory region for compact per-stage tables. The final
stages are specialized: the implementation handles the small
constant-twiddle stages directly, and when `log2(N)` is odd it fuses the
final radix-4 stage (`L = 8`) with the radix-2 stage.

The transform runs in place: the input array is overwritten by the FFT
output. The output is in bit-reversed order.

## 2. Repository layout

``` text
APARA_fft_operation/
├── bin/
│   ├── mcode_align
│   ├── mcode_assemble
│   ├── mcode_disassemble
│   ├── mcode_fpu_test
│   ├── mcode_generate_macro
│   ├── mcode_numeric_test
│   └── mcode_run
├── fft_Npt_float64/
│   ├── fftN_new.mcode
│   ├── generate_mcode.py
│   ├── input_result_generator.py
│   ├── accuracy_out.py
│   ├── run.sh
│   ├── run_fft_verification.sh
│   ├── clean.sh
│   └── fft_<N>.mcode
└── Simulation Results.txt
```

### `bin/`: APARA MCode tools

  -----------------------------------------------------------------------
  Executable                          Role in the supplied workflow
  ----------------------------------- -----------------------------------
  `mcode_align`                       Aligns an MCode program before
                                      assembly.

  `mcode_assemble`                    Assembles aligned MCode into an
                                      object file.

  `mcode_disassemble`                 Disassembles an object file into a
                                      readable MCode representation.

  `mcode_run`                         Executes an assembled program in
                                      the simulator.

  `mcode_generate_macro`              MCode macro-generation utility
                                      supplied with the toolchain.

  `mcode_fpu_test`                    Floating-point unit test utility
                                      supplied with the toolchain.

  `mcode_numeric_test`                Numeric test utility supplied with
                                      the toolchain.
  -----------------------------------------------------------------------

The FFT run script directly uses `mcode_align`, `mcode_assemble`,
`mcode_disassemble`, and `mcode_run`. The other executables are included
as supporting toolchain utilities.

These binaries are Linux x86-64 executables. Run them in a compatible
Linux environment (for example, Linux or WSL with the required runtime
libraries).

### `fft_Npt_float64/`: FFT source and execution scripts

  -----------------------------------------------------------------------
  File                                Purpose
  ----------------------------------- -----------------------------------
  `fftN_new.mcode`                    Reference/template MCode. It
                                      contains the runnable 64-point
                                      reference program and reusable
                                      blocks used to generate other FFT
                                      sizes.

  `generate_mcode.py`                 Selects, orders, parameterizes, and
                                      combines reference blocks to create
                                      `fft_<N>.mcode`.

  `input_result_generator.py`         Generates random complex float64
                                      inputs, twiddle factors, and NumPy
                                      reference FFT outputs.

  `run.sh`                            Aligns, assembles, disassembles,
                                      and simulates a selected FFT MCode
                                      program.

  `run_fft_verification.sh`           Runs the complete test-vector
                                      generation, MCode generation,
                                      simulation, and accuracy-report
                                      workflow.

  `accuracy_out.py`                   Reads the simulator log and
                                      produces an accuracy/performance
                                      report.

  `clean.sh`                          Removes generated intermediate
                                      files and text/map outputs in the
                                      working directory.

  `fft_<N>.mcode`                     Generated FFT programs for
                                      supported transform lengths.
  -----------------------------------------------------------------------

Supported FFT lengths are powers of two from **16 through 2048**. The
generator limits the size because the simulator data memory is 8192
64-bit words and the implementation uses `3N` words: `2N` words for
complex input/output data and `N` words for `N/2` complex twiddle
factors.

## 3. Input, memory layout, and reference output

`input_result_generator.py` creates random complex input samples (real
and imaginary components independently selected from
`[-1,000,000, +1,000,000]`) and the twiddle factors. NumPy's
`numpy.fft.fft` is used to calculate the reference result.

The memory layout is expressed in 64-bit words:

  ------------------------------------------------------------------------
  Word range            Contents                                      Size
  --------------------- --------------------- ----------------------------
  `0` to `2N - 1`       `x[0]` through                          `2N` words
                        `x[N-1]`, real and    
                        imaginary components  
                        interleaved           

  `2N` to `3N - 1`      `W_N^k`, for                             `N` words
                        `0 <= k < N/2`, real  
                        and imaginary         
                        components            
                        interleaved           

  **Total**             Input/output data and               **`3N` words**
                        twiddle factors       
  ------------------------------------------------------------------------

The generated files are:

-   `data.map`: Float64 values encoded as 16-digit IEEE-754 hexadecimal
    words, loaded by the simulator.
-   `input.txt`: Human-readable input samples and twiddle factors.
-   `result.txt`: Reference FFT output in the simulator's comparison
    format, stored in bit-reversed order.
-   `output.txt`: Human-readable reference FFT output in bit-reversed
    order.

The generated test data is random. Consequently, separate runs can use
different input vectors and produce different numerical outputs and
error values.

## 4. Running the FFT verification

Run the commands from the `fft_Npt_float64/` directory.

### Requirements

-   Linux or WSL with the supplied Linux x86-64 binaries executable.
-   Python 3.
-   NumPy (`python3 -m pip install numpy`).
-   Bash.

Make the shell scripts executable if necessary:

``` bash
chmod +x run.sh run_fft_verification.sh clean.sh
```

### Run the complete workflow

For example, to verify a 256-point FFT:

``` bash
cd fft_Npt_float64
./run_fft_verification.sh 256
```

If no size is supplied, the script prompts for `N`:

``` bash
./run_fft_verification.sh
```

The workflow performs these steps:

1.  **Generate test vectors**

    ``` bash
    echo "256" | python3 input_result_generator.py
    ```

    Creates `data.map`, `input.txt`, `result.txt`, and `output.txt`.

2.  **Generate the FFT MCode**

    ``` bash
    python3 generate_mcode.py 256
    ```

    Reads `fftN_new.mcode` and writes `fft_256.mcode`.

3.  **Align, assemble, disassemble, and simulate**

    ``` bash
    ./run.sh fft_256
    ```

    This creates `fft_256.aligned.mcode`, `fft_256.obj`,
    `fft_256.disass.mcode`, and `run.log`. The simulator loads
    `data.map` and uses `result.txt` as the reference for output
    comparison.

4.  **Generate the report**

    ``` bash
    python3 accuracy_out.py
    ```

    Parses `run.log` and writes `accuracy_report.txt`, including
    numerical-error and execution statistics.

### Run the steps individually

``` bash
cd fft_Npt_float64

python3 input_result_generator.py
python3 generate_mcode.py 256
./run.sh fft_256
python3 accuracy_out.py
```

When running the steps individually, enter the same FFT size when
prompted by the input generator and accuracy-report script. The
generated test vectors and MCode must correspond to the same `N`.

## 5. Generated files and reports

The main outputs of a verification run are:

  -----------------------------------------------------------------------
  Output                              Description
  ----------------------------------- -----------------------------------
  `fft_<N>.mcode`                     Generated APARA MCode program for
                                      the selected FFT length.

  `fft_<N>.aligned.mcode`             Aligned MCode passed to the
                                      assembler.

  `fft_<N>.obj`                       Assembled object program executed
                                      by the simulator.

  `fft_<N>.disass.mcode`              Disassembly of the assembled
                                      object.

  `run.log`                           Simulator output and comparison
                                      log.

  `accuracy_report.txt`               Detailed numerical accuracy and
                                      execution report.

  `data.map`                          Simulator memory initialization
                                      data.

  `result.txt`                        Golden/reference output used for
                                      comparison.

  `input.txt`, `output.txt`           Human-readable input and reference
                                      output.
  -----------------------------------------------------------------------

`accuracy_out.py` reports maximum and average relative error, maximum
and average absolute error, RMS error, data-memory usage, executed
bundles (ticks), non-null instructions, instructions per bundle (IPB),
and bundle efficiency.

The bundle efficiency is calculated as:

\[ `\text{Efficiency}`{=tex} =
`\frac{\text{IPB}}{8}`{=tex}`\times 100`{=tex}%. \]

Here, 8 is the maximum number of instruction slots in a bundle.

## 6. Recorded simulation results

`Simulation Results.txt` contains the recorded execution statistics for
FFT sizes from 16 to 2048.

## 7. Cleaning generated files

From `fft_Npt_float64/`, run:

``` bash
./clean.sh
```

This removes generated aligned MCode, object files, disassemblies, logs,
text files, and map files in that directory. It does **not** remove the
reference template or the generated `fft_<N>.mcode` source files.

If you want to preserve a previous run's inputs, outputs, or accuracy
report, copy them elsewhere before cleaning.

## 8. Notes

-   Run the workflow from `fft_Npt_float64/`; `run.sh` uses paths
    relative to that directory to locate `../bin/`.
-   Generate the input/reference files and FFT MCode for the same
    transform length before running the simulator.
-   The FFT output is in bit-reversed order, matching the
    reference-output generation.
-   The provided `Simulation Results.txt` is a record of previously
    collected simulator statistics. Use `accuracy_report.txt` and
    `run.log` from a fresh run for that run's detailed verification
    results.
