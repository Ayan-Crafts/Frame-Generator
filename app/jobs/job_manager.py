import json
import uuid
from datetime import datetime
from pathlib import Path


class JobManager:

    def __init__(self):
        self.jobs_directory = (
            Path.home() /
            ".frame-generator" /
            "jobs"
        )

        self.jobs_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

    # --------------------------------------------------
    # Create / update job
    # --------------------------------------------------

    def create_job(
        self,
        input_directory: str,
        output_directory: str,
        videos: list[Path],
    ):

        job_id = str(uuid.uuid4())

        job = {
            "job_id": job_id,
            "input_directory": input_directory,
            "output_directory": output_directory,
            "videos": [
                str(video)
                for video in videos
            ],
            "status": "created",
            "current_video": None,
            "completed_videos": [],
            "created_at": self._timestamp(),
            "updated_at": self._timestamp(),
        }

        self._save(
            job_id,
            job,
        )

        return job

    def update_job(
        self,
        job_id: str,
        **updates,
    ):

        job = self.load_job(job_id)

        if not job:
            return

        job.update(updates)

        job["updated_at"] = (
            self._timestamp()
        )

        self._save(
            job_id,
            job,
        )

    # --------------------------------------------------
    # Load
    # --------------------------------------------------

    def load_job(
        self,
        job_id: str,
    ):

        path = (
            self.jobs_directory /
            f"{job_id}.json"
        )

        if not path.exists():
            return None

        try:

            with path.open(
                "r",
                encoding="utf-8",
            ) as file:

                return json.load(file)

        except (
            OSError,
            json.JSONDecodeError,
        ):

            return None

    # --------------------------------------------------
    # Find unfinished jobs
    # --------------------------------------------------

    def unfinished_jobs(self):

        jobs = []

        for path in self.jobs_directory.glob(
            "*.json"
        ):

            try:

                with path.open(
                    "r",
                    encoding="utf-8",
                ) as file:

                    job = json.load(file)

                if job.get("status") in {
                    "created",
                    "processing",
                    "paused",
                    "stopped",
                }:

                    jobs.append(job)

            except (
                OSError,
                json.JSONDecodeError,
            ):

                continue

        return jobs

    # --------------------------------------------------
    # Complete
    # --------------------------------------------------

    def complete_job(
        self,
        job_id: str,
    ):

        self.update_job(
            job_id,
            status="completed",
            current_video=None,
        )

    # --------------------------------------------------
    # Cancel completely
    # --------------------------------------------------

    def cancel_job(
        self,
        job_id: str,
    ):

        path = (
            self.jobs_directory /
            f"{job_id}.json"
        )

        try:

            if path.exists():
                path.unlink()

        except OSError:

            pass

    # --------------------------------------------------
    # Timestamp
    # --------------------------------------------------

    def _timestamp(self):

        return datetime.now().isoformat(
            timespec="seconds"
        )

    # --------------------------------------------------
    # Save
    # --------------------------------------------------

    def _save(
        self,
        job_id: str,
        job: dict,
    ):

        path = (
            self.jobs_directory /
            f"{job_id}.json"
        )

        temporary = (
            path.with_suffix(".tmp")
        )

        with temporary.open(
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                job,
                file,
                indent=2,
            )

        # Atomic replacement prevents a partially
        # written job file if the application crashes.
        temporary.replace(path)