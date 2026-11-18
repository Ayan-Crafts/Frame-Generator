from dataclasses import dataclass
from pathlib import Path

from PIL import Image


@dataclass
class ResumeInfo:
    completed: bool
    resume_frame: int
    existing_frames: int


class ResumeManager:

    COMPLETE_MARKER = ".complete"
    TAIL_FRAMES_TO_VERIFY = 8

    def inspect(self, output_directory: Path) -> ResumeInfo:

        if not output_directory.exists():
            return ResumeInfo(
                completed=False,
                resume_frame=1,
                existing_frames=0,
            )

        marker = (
            output_directory /
            self.COMPLETE_MARKER
        )

        if marker.exists():
            return ResumeInfo(
                completed=True,
                resume_frame=0,
                existing_frames=0,
            )

        frames = self._get_frame_numbers(
            output_directory
        )

        if not frames:
            return ResumeInfo(
                completed=False,
                resume_frame=1,
                existing_frames=0,
            )

        expected = 1
        last_valid = 0

        # Find the contiguous run 1..N first (cheap), then validate. FFmpeg
        # writes frames sequentially, so a partially written file can only
        # exist at the tail of a run; frames before it were validated when
        # that earlier run ended. The tail gets a full decode check, every
        # other frame a cheap size check.
        contiguous = []
        for frame_number in frames:
            if frame_number != expected:
                break
            contiguous.append(frame_number)
            expected += 1

        tail_start = max(0, len(contiguous) - self.TAIL_FRAMES_TO_VERIFY)

        for position, frame_number in enumerate(contiguous):

            frame_path = (
                output_directory /
                f"{frame_number:06d}.jpg"
            )

            if position >= tail_start:
                valid = self._is_valid_image(frame_path)
            else:
                valid = self._has_content(frame_path)

            if not valid:
                break

            last_valid = frame_number

        # Remove anything after the valid sequence.
        self._remove_from_frame(
            output_directory,
            last_valid + 1,
        )

        return ResumeInfo(
            completed=False,
            resume_frame=last_valid + 1,
            existing_frames=last_valid,
        )

    def mark_complete(
        self,
        output_directory: Path,
    ):

        marker = (
            output_directory /
            self.COMPLETE_MARKER
        )

        marker.touch()

    def remove_complete_marker(
        self,
        output_directory: Path,
    ):

        marker = (
            output_directory /
            self.COMPLETE_MARKER
        )

        if marker.exists():
            marker.unlink()

    def _get_frame_numbers(
        self,
        output_directory: Path,
    ) -> list[int]:

        numbers = []

        for path in output_directory.glob(
            "*.jpg"
        ):

            try:
                number = int(path.stem)

                if number > 0:
                    numbers.append(number)

            except ValueError:
                continue

        return sorted(numbers)

    @staticmethod
    def _has_content(path: Path) -> bool:
        try:
            return path.stat().st_size > 0
        except OSError:
            return False

    def _is_valid_image(
        self,
        path: Path,
    ) -> bool:

        # PIL's verify() does not decode JPEG data, so a file truncated by
        # an interrupted FFmpeg run would pass it. A complete JPEG ends with
        # the EOI marker (FF D9); check that, then fully decode.
        try:
            size = path.stat().st_size
            if size < 4:
                return False
            with path.open("rb") as handle:
                handle.seek(-2, 2)
                if handle.read(2) != b"\xff\xd9":
                    return False

            with Image.open(path) as image:
                image.load()

            return True

        except (
            OSError,
            ValueError,
            SyntaxError,
        ):
            return False

    def _remove_from_frame(
        self,
        output_directory: Path,
        frame_number: int,
    ):

        for path in output_directory.glob(
            "*.jpg"
        ):

            try:
                number = int(path.stem)

            except ValueError:
                continue

            if number >= frame_number:

                try:
                    path.unlink()
                except OSError:
                    pass