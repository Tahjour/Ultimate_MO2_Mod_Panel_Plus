from setuptools import setup, Extension
from Cython.Build import cythonize

extensions = [
    Extension(
        "esp_viewer.core._classify_fields_fast",
        ["esp_viewer/core/_classify_fields_fast.pyx"],
    )
]

setup(
    name="esp_viewer_fast",
    ext_modules=cythonize(extensions, language_level=3),
)
