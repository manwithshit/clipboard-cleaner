"""Setuptools compatibility shim for editable installs on older pip versions."""

from setuptools import find_packages, setup


setup(
    name='clipboard-cleaner',
    version='0.1.0',
    description='macOS clipboard cleaner panel for Claude Code / Ghostty terminal output.',
    packages=find_packages(),
    python_requires='>=3.9',
    install_requires=[
        'pyperclip',
        'wcwidth',
    ],
    extras_require={
        'test': ['pytest'],
    },
    entry_points={
        'console_scripts': [
            'clipboard-cleaner=clipboard_cleaner.cli:main',
        ],
    },
)
