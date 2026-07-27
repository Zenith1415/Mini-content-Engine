from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, HttpUrl

class GenerateRequest(BaseModel):
    product_name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=2000)
    product_image_url: HttpUrl | None = None

class GenerateResponse(BaseModel):
    job_id: UUID
    status: str

class JobResponse(BaseModel):
    job_id: UUID
    status: str
    product_name: str
    description: str
    reference_image_url: str | None
    generated_prompt: str | None
    image_url: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime
    @classmethod
    def from_job(cls, job) -> "JobResponse":
        return cls(
            job_id=job.id,
            status=job.status,
            product_name=job.product_name,
            description=job.description,
            reference_image_url=job.reference_image_url,
            generated_prompt=job.generated_prompt,
            image_url=job.image_url,
            error=job.error_message,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )