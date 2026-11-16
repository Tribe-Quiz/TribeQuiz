from pydantic import BaseModel, Field


class SignupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=256)


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=1, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=256)


class ForgotPasswordRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8, max_length=256)


class GoogleLoginRequest(BaseModel):
    credential: str = Field(min_length=1, max_length=8192)
    nonce: str = Field(min_length=32, max_length=128)


class StartAttemptRequest(BaseModel):
    culture_id: int = Field(gt=0)


class AnswerRequest(BaseModel):
    question_id: int = Field(gt=0)
    selected_index: int = Field(ge=-1, le=3)
