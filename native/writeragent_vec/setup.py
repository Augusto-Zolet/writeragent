from setuptools import setup, Extension
from Cython.Build import cythonize
import os
import platform

# Determine architecture flags
extra_compile_args = []
system = platform.system()
machine = platform.machine().lower()

if system == "Windows":
    extra_compile_args.append("/O2")
else:
    extra_compile_args.append("-O3")

# Only apply WRITERAGENT_ARCH logic on Linux x86_64
if system == "Linux" and (machine == "x86_64" or machine == "amd64"):
    arch = os.environ.get("WRITERAGENT_ARCH", "x86-64-v2")
    if arch == "x86-64-v1":
        arch = "x86-64"
    extra_compile_args.append(f"-march={arch}")

extensions = [
    Extension(
        "writeragent_vec.pack",
        ["src/writeragent_vec/pack.pyx"],
        extra_compile_args=extra_compile_args,
    )
]

setup(
    ext_modules=cythonize(
        extensions,
        language_level=3,
        compiler_directives={
            'emit_code_comments': False,
        }
    ),
)
