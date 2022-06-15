#!/usr/bin/env python3
import setuptools

with open("README.md", "r", encoding="utf-8") as readme:
    long_description = readme.read()

setuptools.setup(
    name="solarsurfer2",
    version="0.0.1",
    author="Blue Robotics",
    description="☀️🏄‍♂️",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=setuptools.find_packages(),
    python_requires=">=3.6",
    install_requires=[
        "fastapi == 0.63.0",
        "fastapi-versioning == 0.9.1",
        "pynmea2 == 1.18.0",
    ],
)
