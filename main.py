import sys

from pipeline import full_pipeline


def main() -> int:
	if len(sys.argv) != 2:
		print("Usage: python main.py <audio_path>")
		return 1

	audio_path = sys.argv[1]
	full_pipeline(audio_path)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())