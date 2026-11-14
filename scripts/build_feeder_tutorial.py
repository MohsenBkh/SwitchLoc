"""Build the reviewed Persian tutorial with XeLaTeX and install it as Help.

Requires a TeX distribution with XeLaTeX, xepersian and the packages named
in the source. Run from any directory: python scripts/build_feeder_tutorial.py
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'SwitchLoc_Feeder_Tutorial_FA.tex'
OUTPUT = ROOT / 'build_assets/help/SwitchLoc_Guide_FA.pdf'


def main():
    engine = shutil.which('xelatex')
    if not engine:
        raise SystemExit('XeLaTeX not found; install a TeX distribution with xepersian.')
    with tempfile.TemporaryDirectory(prefix='switchloc-guide-') as temp:
        cmd = [engine, '-interaction=nonstopmode', '-halt-on-error',
               '-output-directory', temp, str(SOURCE)]
        for _ in range(2):
            subprocess.run(cmd, cwd=ROOT, check=True)
        pdf = Path(temp) / (SOURCE.stem + '.pdf')
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pdf, OUTPUT)
    print(f'Installed {OUTPUT}')


if __name__ == '__main__':
    main()
