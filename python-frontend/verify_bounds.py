"""Check bounds for compiled list operations and array file reads."""
import argparse
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from translate import translate


def verify_array_file(gibbon, env):
    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        data = root / 'rows.txt'
        for name, argument, options in (
            ('runtime', 'Nothing', ['--array-input', str(data), '--array-input-length', '2']),
            ('literal', 'Just ("rows.txt", 2)', []),
        ):
            source = root / (name + '.hs')
            source.write_text(
                'import Gibbon.Vector\n\n'
                'gibbon_main =\n'
                '    let rows :: Vector Int\n'
                f'        rows = readArrayFile ({argument})\n'
                '    in if vlength rows == 2 then vnth rows 0 + vnth rows 1 else vlength rows\n'
            )
            compiled = subprocess.run(
                [str(gibbon), '--hs', '--packed', '--cc=gcc', '--to-exe', str(source)],
                cwd=root, env=env, capture_output=True, text=True, timeout=180,
            )
            assert compiled.returncode == 0, (name, compiled.stdout, compiled.stderr)
            for rows, error in (
                ('11\n22\n', None),
                ('11\n22\n33\n', 'readArrayFile: input contains more lines than expected'),
                ('11\n', 'readArrayFile: input contains fewer lines than expected'),
            ):
                data.write_text(rows)
                run = subprocess.run(
                    [str(source.with_suffix('.exe')), *options], cwd=root, env=env,
                    capture_output=True, text=True, timeout=15,
                )
                details = name, rows, run.returncode, run.stdout, run.stderr
                if error is None:
                    assert run.returncode == 0 and run.stdout.strip() == '33', details
                else:
                    assert run.returncode == 1 and error in run.stderr, details
            print(f'readArrayFile ({name} length): exact, excess, and short input PASS', flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gibbon', required=True, type=Path)
    parser.add_argument('--gibbon-root', required=True, type=Path)
    args = parser.parse_args()
    build = Path(__file__).resolve().parent / 'build/bounds'
    build.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, GIBBONDIR=str(args.gibbon_root.resolve()))
    cases = {
        'read_high': '    values = [1] * 2\n    return values[2]\n',
        'read_low': '    values = [1] * 2\n    return values[-3]\n',
        'read_empty': '    values = [1] * 0\n    return values[0]\n',
        'write_high': '    values = [1] * 2\n    values[2] = 9\n    return values[0]\n',
    }
    records = []
    for name, body in cases.items():
        source = 'def main() -> int:\n' + body
        namespace = {}
        exec(compile(source, name + '.py', 'exec'), namespace)
        try:
            namespace['main']()
        except IndexError:
            pass
        else:
            raise AssertionError('reference did not raise IndexError')
        hs = build / (name + '.hs')
        hs.write_text(translate(source, name + '.py'))
        compiled = subprocess.run([str(args.gibbon.resolve()), '--hs', '--packed', '--cc=gcc', '--to-exe', str(hs)], env=env, capture_output=True, text=True, timeout=180)
        (build / (name + '.compile.log')).write_text(compiled.stdout + compiled.stderr)
        assert compiled.returncode == 0, compiled.stderr
        run = subprocess.run([str(hs.with_suffix('.exe'))], env=env, capture_output=True, text=True, timeout=15)
        assert run.returncode != 0 and 'list index out of bounds' in run.stdout + run.stderr, (name, run.returncode, run.stdout, run.stderr)
        records.append(dict(case=name, python_error='IndexError', native_returncode=run.returncode, native_message=(run.stdout + run.stderr).strip()))
        (build / 'results.json').write_text(json.dumps(records, indent=2) + '\n')
        print(f'{name}: Python IndexError; native bounds failure PASS', flush=True)
    print(f'{len(records)} bounds checks passed (native process failure, not Python exceptions)')
    verify_array_file(args.gibbon.resolve(), env)


if __name__ == '__main__':
    main()
