from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main() -> None:
    output_dir = Path("assets")
    output_dir.mkdir(exist_ok=True)

    font_paths = [
        Path(r"C:\Windows\Fonts\seguisb.ttf"),
        Path(r"C:\Windows\Fonts\arialbd.ttf"),
    ]
    font_path = next((path for path in font_paths if path.exists()), None)

    images = []
    for size in [16, 24, 32, 48, 64, 128, 256]:
        image = Image.new("RGBA", (size, size), (18, 18, 22, 255))
        draw = ImageDraw.Draw(image)

        for y in range(size):
            color = int(28 + (y / size) * 34)
            draw.line([(0, y), (size, y)], fill=(color, 24, 54, 255))

        radius = max(2, size // 7)
        border = max(1, size // 18)
        draw.rounded_rectangle(
            [1, 1, size - 2, size - 2],
            radius=radius,
            outline=(0, 220, 190, 255),
            width=border,
        )

        font_size = max(8, int(size * 0.44))
        font = ImageFont.truetype(str(font_path), font_size) if font_path else ImageFont.load_default()
        text = "DJ"
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (size - text_width) / 2
        y = (size - text_height) / 2 - int(size * 0.03)
        draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))
        images.append(image)

    icon_path = output_dir / "dj.ico"
    images[-1].save(
        icon_path,
        sizes=[(image.size[0], image.size[1]) for image in images],
        append_images=images[:-1],
    )
    print(icon_path)


if __name__ == "__main__":
    main()

