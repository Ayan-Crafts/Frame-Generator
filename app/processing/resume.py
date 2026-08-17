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

        for frame_number in frames:

            if frame_number != expected:
                break

            frame_path = (
                output_directory /
                f"{frame_number:06d}.jpg"
            )

            if not self._is_valid_image(
                frame_path
            ):
                self._remove_from_frame(
                    output_directory,
                    frame_number,
                )
                break

            last_valid = frame_number
            expected += 1

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

    def _is_valid_image(
        self,
        path: Path,
    ) -> bool:

        try:

            with Image.open(path) as image:
                image.verify()

            return True

        except (
            OSError,
            ValueError,
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