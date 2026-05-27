from setuptools import setup, Extension
from Cython.Build import cythonize
import os
import platform

# Determine architecture flags
# Only apply -march on x86_64 and not on macOS (where -arch is handled by cibuildwheel/compiler)
extra_compile_args = ["-O3"]
system = platform.system()
machine = platform.machine().lower()

# Only apply WRITERAGENT_ARCH logic on Linux/Windows x86_64
if system != "Darwin" and (machine == "x86_64" or machine == "amd64"):
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
    name="writeragent_vec",
    version="0.1.0",
    package_dir={"": "src"},
    packages=["writeragent_vec"],
    ext_modules=cythonize(
        extensions,
        language_level=3,
        compiler_directives={
            'emit_code_comments': False,
        }
    ),
)
