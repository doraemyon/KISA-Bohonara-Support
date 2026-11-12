"""Run the Helsinki-NLP Korean-to-English OPUS-MT model on the CPU."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import urllib.request
import zipfile
from functools import cache
from pathlib import Path
from typing import Callable


MODEL_URL = (
    "https://object.pouta.csc.fi/Tatoeba-MT-models/kor-eng/"
    "opusTCv20210807-sepvoc_transformer-big_2022-07-28.zip"
)
MODEL_SIZE = 776_542_556
MODEL_SHA256 = "9132ed606b6964656520931d96a4a6afc7ddc7d55ca5438e1d403db0c05492ef"


def model_directory() -> Path:
    value = os.environ.get("KISA_OFFLINE_MODEL_DIR")
    if not value:
        raise RuntimeError("Offline translation model is not configured.")
    return Path(value)


def model_is_ready(path: Path) -> bool:
    marker = path / ".ready"
    return (
        marker.is_file()
        and marker.read_text(encoding="ascii").strip() == MODEL_SHA256
        and all((path / name).is_file() for name in ("model.bin", "source.spm", "target.spm"))
    )


def download_model(archive: Path) -> None:
    digest = hashlib.sha256()
    size = 0
    with urllib.request.urlopen(MODEL_URL, timeout=30) as response, archive.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > MODEL_SIZE:
                raise RuntimeError("The offline model archive exceeded its expected size.")
            digest.update(chunk)
            output.write(chunk)
    if size != MODEL_SIZE or digest.hexdigest() != MODEL_SHA256:
        raise RuntimeError("The offline model archive did not match its pinned checksum.")


def prepare_model(path: Path) -> None:
    if model_is_ready(path):
        return

    from ctranslate2.converters import OpusMTConverter

    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=path.parent, prefix="opus-setup-") as workdir:
        work = Path(workdir)
        archive = work / "model.zip"
        source = work / "source"
        source.mkdir()
        download_model(archive)
        with zipfile.ZipFile(archive) as bundle:
            for name in bundle.namelist():
                member = Path(name)
                if member.name != name:
                    continue
                if member.suffix == ".vocab":
                    # The Marian release uses one token per line. CTranslate2
                    # expects the same token IDs written as a mapping.
                    tokens = bundle.read(name).decode("utf-8").rstrip("\n").split("\n")
                    (source / name).write_text(
                        "".join(
                            f"{json.dumps(token, ensure_ascii=False)}: {index}\n"
                            for index, token in enumerate(tokens)
                        ),
                        encoding="utf-8",
                    )
                elif member.suffix in {".npz", ".yml", ".spm"}:
                    with bundle.open(name) as original, (source / name).open("wb") as output:
                        shutil.copyfileobj(original, output)

        compiled = work / "converted"
        OpusMTConverter(str(source)).convert(str(compiled), quantization="int8")
        for name in ("source.spm", "target.spm"):
            shutil.copyfile(source / name, compiled / name)

        path.mkdir(exist_ok=True)
        for file in compiled.iterdir():
            file.replace(path / file.name)
        (path / ".ready").write_text(MODEL_SHA256 + "\n", encoding="ascii")


@cache
def load_model(path: Path):
    if not model_is_ready(path):
        raise RuntimeError("Offline translation model is not prepared.")
    try:
        from ctranslate2 import Translator
        from sentencepiece import SentencePieceProcessor
    except ImportError as error:
        raise RuntimeError("Offline translation runtime is unavailable.") from error

    source = SentencePieceProcessor(model_file=str(path / "source.spm"))
    target = SentencePieceProcessor(model_file=str(path / "target.spm"))
    engine = Translator(str(path), device="cpu", compute_type="int8", intra_threads=2)
    return source, target, engine


def translate(segment: str, accepts: Callable[[str], bool] | None = None) -> str:
    source, target, engine = load_model(model_directory())
    tokens = source.encode(segment, out_type=str)
    result = engine.translate_batch(
        [tokens], beam_size=4, num_hypotheses=3 if accepts else 1, replace_unknowns=True
    )
    candidates = [target.decode(tokens).strip() for tokens in result[0].hypotheses]
    return next((value for value in candidates if accepts is None or accepts(value)), candidates[0])


if __name__ == "__main__":
    prepare_model(model_directory())
    if "update" not in translate("보안 업데이트를 적용하십시오.").lower():
        raise RuntimeError("Offline translation failed its security-update check.")
    print("Offline OPUS-MT model is ready.")
