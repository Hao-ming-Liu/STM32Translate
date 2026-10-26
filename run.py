"""Shared entry point for the windowed shell and hidden console worker."""
import argparse
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description='STM32 离线英译中小窗')
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--model', type=Path)
    args = parser.parse_args()
    if args.worker:
        from stm32translate.worker import main as worker_main
        if sys.stdin is not None:
            sys.stdin.reconfigure(encoding='utf8')
            sys.stdout.reconfigure(encoding='utf8', line_buffering=True)
        root = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
        worker_main(args.model or root / 'models/en_zh')
    else:
        from stm32translate.app import main as app_main
        app_main()


if __name__ == '__main__':
    main()
