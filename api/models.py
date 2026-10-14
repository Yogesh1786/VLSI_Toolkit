"""Request bodies shared by the API routers (validated automatically by FastAPI)."""

from pydantic import BaseModel, Field


class SourceFile(BaseModel):
    """One text file sent by the browser."""

    name: str = Field(..., examples=["counter.v"])
    text: str


class Files(BaseModel):
    files: list[SourceFile] = Field(..., min_length=1)


class TestbenchRequest(SourceFile):
    module: str | None = None
    cycles: int = Field(100, ge=1, le=1_000_000)
    period: int = Field(10, ge=1, le=100_000)


class VcdRequest(SourceFile):
    glitch: int = Field(2, ge=1)
    x_after: int | None = Field(None, ge=0)


class AxiRequest(SourceFile):
    timeout: int = Field(16, ge=1, le=100_000)


class FloorplanRequest(BaseModel):
    def_file: SourceFile
    lefs: list[SourceFile] = []


class LibertyCellRequest(SourceFile):
    cell: str


class SweepRequest(SourceFile):
    param: str = Field(..., min_length=1)
    values: str = Field(..., min_length=1)


class MeasureRequest(SourceFile):
    signals: list[str] = []
    ref: str | None = None
    vdd: float | None = Field(None, ge=0)


class CompareFilesRequest(BaseModel):
    old: list[SourceFile] = Field(..., min_length=1)
    new: list[SourceFile] = Field(..., min_length=1)


class CompareFileRequest(BaseModel):
    old: SourceFile
    new: SourceFile


class SvaRequest(Files):
    module: str | None = None
    axi: bool = True
    fsm: bool = True
    onehot: bool = True
    outputs: bool = True
    covers: bool = True


class SdcRequest(SourceFile):
    rtl: list[SourceFile] = (
        []
    )  # optional top-level RTL: port-name and I/O-coverage checks
    module: str | None = None
