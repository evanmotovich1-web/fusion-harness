import sys


def count(text):
    return {"lines": len(text.splitlines()), "words": len(text.split()), "chars": len(text)}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv:
        try:
            with open(argv[0], encoding="utf-8") as handle:
                text = handle.read()
        except OSError as error:
            print(f"wordstats: cannot read {argv[0]!r}: {error}", file=sys.stderr)
            return 2
    else:
        text = sys.stdin.read()
    stats = count(text)
    print(f"Lines: {stats['lines']}\nWords: {stats['words']}\nCharacters: {stats['chars']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
