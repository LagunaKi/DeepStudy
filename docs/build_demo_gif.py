"""Build the checked-in 90-second portfolio walkthrough from real UI captures."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
OUTPUT = ASSETS / "deepstudy-demo-90s.gif"
SIZE = (1280, 720)
MAIN_FRAME_MS = 12_000
TRANSITION_FRAME_MS = 1_200
TRANSITION_STEPS = 3


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    noto = (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
        if bold
        else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
    )
    dejavu = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    )
    candidates = [
        Path("/System/Library/Fonts/STHeiti Medium.ttc"),
        Path("/System/Library/Fonts/STHeiti Light.ttc"),
        Path(noto),
        Path(dejavu),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def _open_capture(filename: str) -> Image.Image:
    image = Image.open(ASSETS / filename).convert("RGB")
    if image.size != SIZE:
        image = image.resize(SIZE, Image.Resampling.LANCZOS)
    return image


def _caption(image: Image.Image, title: str, subtitle: str) -> Image.Image:
    composed = image.convert("RGBA")
    overlay = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rounded_rectangle((28, 20, 788, 98), radius=18, fill=(15, 23, 42, 218))
    draw.text((52, 33), title, font=_font(24, bold=True), fill=(255, 255, 255, 255))
    draw.text((52, 66), subtitle, font=_font(16), fill=(203, 213, 225, 255))
    return Image.alpha_composite(composed, overlay).convert("RGB")


def _title_card(background: Image.Image) -> Image.Image:
    canvas = background.filter(ImageFilter.GaussianBlur(radius=8)).convert("RGBA")
    shade = Image.new("RGBA", SIZE, (15, 23, 42, 190))
    canvas = Image.alpha_composite(canvas, shade)
    draw = ImageDraw.Draw(canvas)
    title = "DeepStudy"
    subtitle = "基于 LangGraph、GraphRAG 与分层记忆的自适应学习 Agent"
    proof = "真实课程资料 · 可追溯引用 · 可观察工具调用 · 可控长期记忆"
    title_font = _font(64, bold=True)
    subtitle_font = _font(28, bold=True)
    proof_font = _font(20)
    title_box = draw.textbbox((0, 0), title, font=title_font)
    subtitle_box = draw.textbbox((0, 0), subtitle, font=subtitle_font)
    proof_box = draw.textbbox((0, 0), proof, font=proof_font)
    draw.text(
        ((SIZE[0] - (title_box[2] - title_box[0])) / 2, 245),
        title,
        font=title_font,
        fill="white",
    )
    draw.text(
        ((SIZE[0] - (subtitle_box[2] - subtitle_box[0])) / 2, 340),
        subtitle,
        font=subtitle_font,
        fill=(224, 231, 255),
    )
    draw.text(
        ((SIZE[0] - (proof_box[2] - proof_box[0])) / 2, 405),
        proof,
        font=proof_font,
        fill=(191, 219, 254),
    )
    return canvas.convert("RGB")


def build() -> Path:
    rag_sources = _open_capture("rag-sources.jpg")
    scenes = [
        _title_card(rag_sources),
        _caption(
            rag_sources,
            "01 课程资料问答",
            "PDF 结构化切片 · 页码级引用 · 回答可追溯",
        ),
        _caption(
            _open_capture("agent-trace-final.jpg"),
            "02 Agent Trace",
            "Router → Planner → Retriever → Tool → Verifier → Memory",
        ),
        _caption(
            _open_capture("knowledge-graph.jpg"),
            "03 GraphRAG 双视图",
            "学习思维导图与领域知识关系图可随时切换",
        ),
        _caption(
            _open_capture("memory-center.jpg"),
            "04 分层记忆",
            "跨会话记忆可确认、编辑或永久遗忘",
        ),
        _caption(
            _open_capture("learning-profile.jpg"),
            "05 自适应学习画像",
            "U/R/A、练习次数与学习计划持续更新",
        ),
    ]

    frames: list[Image.Image] = []
    durations: list[int] = []
    for index, scene in enumerate(scenes):
        frames.append(scene)
        durations.append(MAIN_FRAME_MS)
        if index == len(scenes) - 1:
            continue
        following = scenes[index + 1]
        for step in range(1, TRANSITION_STEPS + 1):
            frames.append(Image.blend(scene, following, step / (TRANSITION_STEPS + 1)))
            durations.append(TRANSITION_FRAME_MS)

    assert sum(durations) == 90_000, "Demo duration must remain exactly 90 seconds"
    palette_frames = [
        frame.quantize(colors=128, method=Image.Quantize.FASTOCTREE)
        for frame in frames
    ]
    palette_frames[0].save(
        OUTPUT,
        save_all=True,
        append_images=palette_frames[1:],
        duration=durations,
        loop=0,
        optimize=False,
        disposal=2,
    )
    return OUTPUT


if __name__ == "__main__":
    print(build())
