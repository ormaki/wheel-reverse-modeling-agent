from __future__ import annotations

from pathlib import Path
import shutil
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Ellipse, FancyArrowPatch, FancyBboxPatch, Circle, Rectangle, Wedge
from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
FIG_DIR = ROOT / "specs" / "figures"
EXT_FIG_DIR = Path("F:/\u4e71\u4e03\u516b\u7cdf\u8d44\u6599/\u6bd5\u8bbe\u8d44\u6599/\u8bba\u6587\u56fe\u7247\u7d20\u6750")

SOURCE_FIGURES = {
    "stage01": FIG_DIR / "stage01_spokeless_perception_4_2.png",
    "stage02": FIG_DIR / "stage02_pcd_perception_4_3.png",
    "stage03": FIG_DIR / "stage03_hub_grooves_perception_4_4.png",
    "stage04": FIG_DIR / "stage04_spoke_member_diagnosis_4_5.png",
}


def zh(text: str) -> str:
    return text.encode("ascii").decode("unicode_escape")


def setup_font() -> None:
    for font_path in [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
    ]:
        path = Path(font_path)
        if path.exists():
            font_manager.fontManager.addfont(path)
            plt.rcParams["font.sans-serif"] = [font_manager.FontProperties(fname=path).get_name()]
            break
    plt.rcParams["axes.unicode_minus"] = False


def wrap(text: str, width: int = 18) -> str:
    if any("\u4e00" <= ch <= "\u9fff" for ch in text):
        lines: list[str] = []
        current = ""
        for ch in text:
            current += ch
            if len(current) >= width:
                lines.append(current)
                current = ""
        if current:
            lines.append(current)
        return "\n".join(lines)
    return "\n".join(textwrap.wrap(text, width=width, break_long_words=True, replace_whitespace=False))


def add_arrow(fig, start: tuple[float, float], end: tuple[float, float], color: str = "#33556b") -> None:
    fig.patches.append(
        FancyArrowPatch(
            start,
            end,
            transform=fig.transFigure,
            arrowstyle="-|>",
            mutation_scale=18,
            linewidth=1.8,
            color=color,
            shrinkA=0,
            shrinkB=0,
        )
    )


def draw_card(ax, x: float, y: float, w: float, h: float, title: str, body: str, accent: str) -> None:
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.018,rounding_size=0.03",
            linewidth=1.2,
            edgecolor=accent,
            facecolor="#f7fbfd",
        )
    )
    title_size = 9.7 if h < 0.14 else 11.5
    body_size = 8.2 if h < 0.14 else 9.6
    body_width = 18 if h < 0.14 else 16
    ax.text(x + 0.03, y + h - 0.026, title, fontsize=title_size, fontweight="bold", color="#102f43", va="top")
    ax.text(x + 0.03, y + h - 0.066, wrap(body, body_width), fontsize=body_size, color="#20272d", va="top", linespacing=1.20)


def draw_method_axis(ax, icon_kind: str, cards: list[tuple[str, str]], accent: str) -> None:
    ax.set_axis_off()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.text(0.04, 0.96, zh(r"\u4e09\u7ef4\u611f\u77e5\u5165\u53e3"), fontsize=13, fontweight="bold", color="#102f43", va="top")
    draw_stage_schematic(ax, icon_kind, accent)
    ax.text(
        0.50,
        0.48,
        zh(r"\u5207\u7247\u6216\u6295\u5f71\u540e\u8f6c\u4e3a\u53ef\u5efa\u6a21\u53c2\u6570"),
        fontsize=9.2,
        color="#425767",
        ha="center",
        va="center",
    )
    y_positions = [0.325, 0.185, 0.045]
    for idx, ((title, body), y) in enumerate(zip(cards, y_positions), start=1):
        draw_card(ax, 0.07, y, 0.86, 0.105, f"{idx}. {title}", body, accent)
        if idx < len(cards):
            ax.annotate(
                "",
                xy=(0.50, y - 0.025),
                xytext=(0.50, y - 0.002),
                arrowprops=dict(arrowstyle="-|>", color=accent, lw=1.5),
            )


def draw_stage_schematic(ax, icon_kind: str, accent: str) -> None:
    import math

    cx, cy = 0.50, 0.73
    if icon_kind == "section":
        ax.add_patch(Ellipse((cx, cy), 0.46, 0.23, angle=-12, fill=False, ec="#7f8d96", lw=1.6))
        ax.add_patch(Ellipse((cx + 0.04, cy - 0.02), 0.34, 0.15, angle=-12, fill=False, ec="#a7b0b6", lw=1.0))
        for offset in [-0.08, -0.04, 0.0, 0.04, 0.08]:
            ax.plot([cx - 0.20, cx + 0.22], [cy + offset, cy + offset - 0.08], color="#c0c8ce", lw=0.7)
        ax.add_patch(Rectangle((cx - 0.025, cy - 0.18), 0.05, 0.36, fc="#d9e6ef", ec=accent, lw=1.2, alpha=0.82))
        ax.text(cx, cy + 0.175, zh(r"\u8f74\u5411\u622a\u5e73\u9762"), fontsize=8.8, ha="center", color="#102f43")
        x = [0.25, 0.30, 0.35, 0.40, 0.48, 0.58, 0.64, 0.70, 0.75]
        y = [0.54, 0.55, 0.51, 0.43, 0.40, 0.42, 0.50, 0.55, 0.55]
        ax.plot(x, y, color=accent, lw=2.0)
        ax.scatter(x, y, s=7, color="#1b6fd0")
        ax.text(0.50, 0.505, zh(r"r-z \u622a\u9762\u8f6e\u5ed3"), fontsize=8.8, ha="center", color="#102f43")
    elif icon_kind == "pcd":
        for radius, lw in [(0.18, 1.5), (0.145, 1.0), (0.055, 1.3)]:
            ax.add_patch(Circle((cx, cy), radius, fill=False, ec="#7f8d96", lw=lw))
        ax.add_patch(Circle((cx, cy), 0.085, fill=False, ec=accent, lw=1.0, ls="--"))
        for i in range(10):
            a = math.radians(i * 36)
            ax.add_patch(Circle((cx + 0.085 * math.cos(a), cy + 0.085 * math.sin(a)), 0.011, fc="white", ec=accent, lw=1.5))
        ax.add_patch(Rectangle((0.24, 0.60), 0.52, 0.12, fc="#d9e6ef", ec=accent, lw=1.0, alpha=0.50))
        ax.text(0.50, 0.535, zh(r"\u7aef\u9762\u6295\u5f71\u8bc6\u522b\u5b54\u4f4d"), fontsize=8.8, ha="center", color="#102f43")
    elif icon_kind == "groove":
        for radius, lw in [(0.19, 1.4), (0.12, 1.0), (0.055, 1.2)]:
            ax.add_patch(Circle((cx, cy), radius, fill=False, ec="#7f8d96", lw=lw))
        for i in range(10):
            a = math.radians(i * 36)
            ax.add_patch(Circle((cx + 0.09 * math.cos(a), cy + 0.09 * math.sin(a)), 0.010, fc="white", ec="#6c757d", lw=1.0))
        for start in [25, 100, 175, 250, 325]:
            ax.add_patch(Wedge((cx, cy), 0.15, start, start + 34, width=0.045, fc="#ffd6d2", ec="#d44d42", lw=1.3))
        ax.add_patch(Rectangle((0.25, 0.62), 0.50, 0.08, fc="#d9e6ef", ec=accent, lw=1.0, alpha=0.45))
        ax.text(0.50, 0.535, zh(r"\u8f6e\u5fc3\u5c40\u90e8\u5207\u7247\u627e\u51f9\u69fd"), fontsize=8.8, ha="center", color="#102f43")
    else:
        for radius, lw in [(0.19, 1.4), (0.12, 1.0), (0.052, 1.2)]:
            ax.add_patch(Circle((cx, cy), radius, fill=False, ec="#7f8d96", lw=lw))
        for i in range(10):
            a = math.radians(i * 36 + 8)
            ax.plot(
                [cx + 0.06 * math.cos(a), cx + 0.165 * math.cos(a)],
                [cy + 0.06 * math.sin(a), cy + 0.165 * math.sin(a)],
                color="#b8c0c6",
                lw=3.0,
                solid_capstyle="round",
            )
        ax.add_patch(Wedge((cx, cy), 0.18, 18, 44, width=0.12, fc="#d8f0e4", ec=accent, lw=1.5, alpha=0.90))
        ax.plot([cx, cx + 0.18], [cy, cy + 0.065], color=accent, lw=1.2, ls="--")
        ax.text(0.50, 0.535, zh(r"\u6309\u89d2\u5ea6\u62c6\u6210\u8f90\u6761\u6210\u5458"), fontsize=8.8, ha="center", color="#102f43")


def show_source(ax, image_path: Path, title: str, crop: tuple[int, int, int, int] | None = None) -> None:
    image = Image.open(image_path).convert("RGB")
    if crop is not None:
        image = image.crop(crop)
    image = ImageOps.expand(image, border=16, fill="white")
    ax.imshow(image)
    ax.set_axis_off()
    ax.set_title(title, fontsize=12.5, fontweight="bold", color="#102f43", pad=8)


def draw_result_panel(ax, title: str, rows: list[tuple[str, str]], accent: str) -> None:
    ax.set_axis_off()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.text(0.04, 0.96, title, fontsize=13, fontweight="bold", color="#102f43", va="top")
    ax.add_patch(
        FancyBboxPatch(
            (0.04, 0.08),
            0.92,
            0.78,
            boxstyle="round,pad=0.02,rounding_size=0.035",
            linewidth=1.3,
            edgecolor="#9aaebc",
            facecolor="#f8fbfc",
        )
    )
    y = 0.78
    for key, value in rows:
        ax.text(0.09, y, key, fontsize=10.8, fontweight="bold", color=accent, va="top")
        ax.text(0.32, y, wrap(value, 14), fontsize=10.0, color="#20272d", va="top", linespacing=1.35)
        y -= 0.145


def create_figure(
    *,
    title: str,
    method_cards: list[tuple[str, str]],
    source_path: Path,
    source_title: str,
    result_rows: list[tuple[str, str]],
    output_name: str,
    icon_kind: str,
    accent: str,
    crop: tuple[int, int, int, int] | None = None,
) -> None:
    fig = plt.figure(figsize=(10.8, 5.8), dpi=240, facecolor="white")
    fig.suptitle(title, fontsize=18, fontweight="bold", color="#123a5a", y=0.965)
    gs = fig.add_gridspec(
        1,
        3,
        width_ratios=[1.05, 1.55, 1.05],
        left=0.045,
        right=0.985,
        bottom=0.09,
        top=0.84,
        wspace=0.16,
    )
    ax_left = fig.add_subplot(gs[0, 0])
    ax_mid = fig.add_subplot(gs[0, 1])
    ax_right = fig.add_subplot(gs[0, 2])
    draw_method_axis(ax_left, icon_kind, method_cards, accent)
    show_source(ax_mid, source_path, source_title, crop)
    draw_result_panel(ax_right, zh(r"\u5efa\u6a21\u4f9d\u636e"), result_rows, accent)
    add_arrow(fig, (0.31, 0.46), (0.34, 0.46), accent)
    add_arrow(fig, (0.68, 0.46), (0.71, 0.46), accent)

    output = FIG_DIR / output_name
    fig.savefig(output, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    EXT_FIG_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(output, EXT_FIG_DIR / output.name)
    print(output)


def main() -> None:
    setup_font()
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    create_figure(
        title=zh(r"\u8f6e\u8f8b\u8f6e\u5fc3\u56de\u8f6c\u4f53\u521b\u5efa\u65b9\u6cd5"),
        icon_kind="section",
        accent="#2b6f9e",
        method_cards=[
            (zh(r"\u8f74\u5411\u5207\u7247"), zh(r"\u6cbf\u65cb\u8f6c\u8f74\u53d6 r-z \u622a\u9762\u70b9\u4e91")),
            (zh(r"\u6392\u9664\u5e72\u6270"), zh(r"\u5f31\u5316\u5b54\u3001\u69fd\u548c\u8f90\u6761\u5c40\u90e8\u622a\u9762")),
            (zh(r"\u56de\u8f6c\u5efa\u6a21"), zh(r"\u7528\u7a33\u5b9a\u4e3b\u8f6e\u5ed3\u751f\u6210\u57fa\u4f53")),
        ],
        source_path=SOURCE_FIGURES["stage01"],
        source_title=zh(r"\u771f\u5b9e\u622a\u9762\u5019\u9009\u4e0e\u62df\u5408\u7ed3\u679c"),
        result_rows=[
            (zh(r"\u8f93\u5165"), zh(r"\u8f6e\u6bc2 STL \u7f51\u683c\u548c\u65cb\u8f6c\u8f74\u4f30\u8ba1")),
            (zh(r"\u8f93\u51fa"), zh(r"\u8f6e\u8f8b\u8f6e\u5ed3\u3001\u8f6e\u5fc3\u8f6e\u5ed3\u548c\u56de\u8f6c\u9762\u8fb9\u754c")),
            (zh(r"\u5efa\u6a21"), zh(r"\u6309\u8be5 r-z \u8f6e\u5ed3\u56f4\u7ed5\u4e2d\u5fc3\u8f74\u751f\u6210\u7a33\u5b9a\u4e3b\u4f53")),
            (zh(r"\u9650\u5236"), zh(r"\u5b54\u4f4d\u3001\u51f9\u69fd\u548c\u8f90\u6761\u7559\u5230\u540e\u7eed\u9636\u6bb5")),
        ],
        output_name="stage01_method_pipeline_slice.png",
    )

    create_figure(
        title=zh(r"\u8f6e\u5fc3 PCD \u5b54\u521b\u5efa\u65b9\u6cd5"),
        icon_kind="pcd",
        accent="#2667d8",
        method_cards=[
            (zh(r"\u7aef\u9762\u6295\u5f71"), zh(r"\u5728\u8f6e\u5fc3\u6b63\u9762\u627e\u5706\u5f62\u5b54\u5019\u9009")),
            (zh(r"\u62df\u5408 PCD"), zh(r"\u7528\u5b54\u4e2d\u5fc3\u6821\u9a8c\u7b49\u89d2\u5ea6\u5206\u5e03")),
            (zh(r"\u9635\u5217\u5207\u9664"), zh(r"\u6309\u5b54\u6570\u3001\u5b54\u5f84\u548c\u534a\u5f84\u51cf\u6750")),
        ],
        source_path=SOURCE_FIGURES["stage02"],
        source_title=zh(r"\u771f\u5b9e PCD \u5b54\u9635\u8bc6\u522b\u7ed3\u679c"),
        result_rows=[
            (zh(r"\u5b54\u6570"), zh(r"10 \u4e2a\u87ba\u6813\u5b54")),
            ("PCD", "200.3 mm"),
            (zh(r"\u5b54\u5f84"), "12.0 mm"),
            (zh(r"\u5efa\u6a21"), zh(r"\u5728\u7a33\u5b9a\u8f6e\u5fc3\u4e3b\u4f53\u4e0a\u6309\u5706\u5468\u9635\u5217\u5207\u9664")),
        ],
        output_name="stage02_method_pipeline_pcd.png",
        crop=(60, 40, 1445, 1425),
    )

    create_figure(
        title=zh(r"\u8f6e\u5fc3\u975e\u5b54\u7279\u5f81\u521b\u5efa\u65b9\u6cd5"),
        icon_kind="groove",
        accent="#c94f45",
        method_cards=[
            (zh(r"\u56fa\u5b9a\u5b54\u4f4d"), zh(r"\u4e0d\u518d\u91cd\u65b0\u6539\u52a8\u4e2d\u5fc3\u5b54\u548c PCD \u5b54")),
            (zh(r"\u5c40\u90e8\u5207\u7247"), zh(r"\u5728\u8f6e\u5fc3\u73af\u5e26\u63d0\u53d6\u51f9\u69fd\u548c\u53f0\u9636")),
            (zh(r"\u8868\u9762\u7ec6\u4fee"), zh(r"\u7528\u6d45\u5207\u9664\u3001\u8865\u5f62\u548c\u8fc7\u6e21\u8fb9\u754c\u6062\u590d")),
        ],
        source_path=SOURCE_FIGURES["stage03"],
        source_title=zh(r"\u771f\u5b9e\u8f6e\u5fc3\u51f9\u69fd\u5019\u9009 overlay"),
        result_rows=[
            (zh(r"\u8f93\u5165"), zh(r"\u5df2\u5b8c\u6210\u7684\u56de\u8f6c\u4e3b\u4f53\u548c PCD \u5b54\u9635")),
            (zh(r"\u7ea2\u8272"), zh(r"\u5f85\u8865\u5145\u7684\u51f9\u69fd\u6216\u5c40\u90e8\u51cf\u6750\u533a\u57df")),
            (zh(r"\u84dd\u8272"), zh(r"\u8f6e\u5fc3\u53ef\u7528\u8fb9\u754c\u548c\u5c40\u90e8\u5206\u6790\u8303\u56f4")),
            (zh(r"\u5efa\u6a21"), zh(r"\u6309\u5c40\u90e8\u8fb9\u754c\u505a\u6d45\u5207\u9664\u3001\u53f0\u9636\u6216\u8865\u5f62")),
        ],
        output_name="stage03_method_pipeline_nonhole.png",
        crop=(55, 35, 1215, 1220),
    )

    create_figure(
        title=zh(r"\u8f90\u6761\u751f\u6210\u4e0e\u4fee\u6b63\u65b9\u6cd5"),
        icon_kind="spoke",
        accent="#28745a",
        method_cards=[
            (zh(r"\u6210\u5458\u5207\u7247"), zh(r"\u6309\u89d2\u5ea6\u62c6\u5206\u8f90\u6761\u6210\u5458\u5e76\u53d6\u5c40\u90e8\u8f6e\u5ed3")),
            (zh(r"\u57fa\u7840\u62c9\u4f38"), zh(r"\u5148\u751f\u6210\u80fd\u8fde\u63a5\u8f6e\u5fc3\u548c\u8f6e\u8f8b\u7684\u7b80\u5355\u4f53")),
            (zh(r"\u5dee\u5f02\u7ec6\u4fee"), zh(r"\u7528\u70b9\u4e91\u548c\u89c6\u89c9\u5bf9\u6bd4\u4fee\u6b63\u8fb9\u754c")),
        ],
        source_path=SOURCE_FIGURES["stage04"],
        source_title=zh(r"\u771f\u5b9e\u8f90\u6761\u6210\u5458\u5dee\u5f02\u8bca\u65ad"),
        result_rows=[
            (zh(r"\u84dd\u8272"), zh(r"\u53c2\u8003STL\u6709\u800c\u5019\u9009CAD\u7f3a\u5c11\u7684\u533a\u57df")),
            (zh(r"\u7ea2\u8272"), zh(r"\u5019\u9009CAD\u591a\u51fa\u6216\u8fb9\u754c\u504f\u79fb\u7684\u533a\u57df")),
            (zh(r"\u6210\u5458"), zh(r"\u6309 m0-m9 \u5206\u522b\u68c0\u67e5\u8f90\u6761\u5c40\u90e8")),
            (zh(r"\u5efa\u6a21"), zh(r"\u6309\u8bc4\u4f30\u53cd\u9988\u4fee\u6b63\u8f90\u6761\u5bbd\u5ea6\u3001\u8fde\u63a5\u548c\u8fc7\u6e21")),
        ],
        output_name="stage04_method_pipeline_spoke.png",
        crop=(0, 0, 1800, 560),
    )


if __name__ == "__main__":
    main()
