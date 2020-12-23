from setuptools import find_packages, setup

with open("README.md") as readme_file:
    readme = readme_file.read()

requirements = ["Click>=7<8", "toml>=0.10.1<1", "dateparser", "pydantic"]

setup(
    author="Oscar Arbeláez",
    author_email="odarbelaeze@gmail.com",
    python_requires=">=3.6",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Natural Language :: English",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
    ],
    description="CodeLog utility.",
    entry_points={"console_scripts": ["codelog=codelog.cli:main"]},
    install_requires=requirements,
    license="MIT license",
    long_description=readme,
    long_description_content_type="text/markdown",
    include_package_data=True,
    keywords="git, code, log, journal",
    name="codelog",
    packages=find_packages(where="src"),
    package_dir={"": "src/", "codelog": "src/codelog"},
    url="https://github.com/coreofscience/python-sap",
    version="0.1.0",
    zip_safe=False,
)
