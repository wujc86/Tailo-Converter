#!/usr/bin/env python3
"""Build the browser database used by the Tailo Converter website.

Input workbooks live in ``source/``.  The generated ``web_database.js`` is
loaded directly by index.html as ``window.TAILO_DB``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
HANJI_SOURCE = ROOT / "source" / "漢字臺羅對照表20260723.xlsx"
IPA_SOURCE = ROOT / "source" / "IPA對照表20260723.xlsx"
OUTPUT = ROOT / "web_database.js"

LANG_ROW_MAP = {0: "俄", 1: "義", 2: "西", 3: "德", 4: "法", 5: "英"}
HEADER_ROW = 6
FIRST_VOWEL_ROW = 7
IPA_SHEET = "2026修訂"
READING_TYPES = ("文", "無", "白", "替", "俗")


def build_hanji_database(path: Path) -> dict[str, dict[str, list[str]]]:
    """Read the two-column Hanji workbook into the website's data format."""
    frame = pd.read_excel(path)
    if "漢字" not in frame.columns:
        raise ValueError("漢字對照表缺少「漢字」欄位")
    # The 2026-07-23 workbook leaves the second header cell blank.  Retain
    # compatibility with earlier files that explicitly name it 「臺羅」.
    tailo_column = "臺羅" if "臺羅" in frame.columns else frame.columns[1]

    entries: dict[str, dict[str, list[str]]] = {}
    for _, row in frame.iterrows():
        if pd.isna(row["漢字"]):
            continue
        char = str(row["漢字"]).strip()
        if not char:
            continue
        entry = entries.setdefault(char, {kind: [] for kind in READING_TYPES})
        if pd.isna(row[tailo_column]):
            continue

        text = str(row[tailo_column]).replace("\r\n", "\n").replace("\r", "\n")
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            kind = "無"
            value = line
            for candidate in READING_TYPES:
                marker = f"{candidate}："
                if line.startswith(marker):
                    kind = candidate
                    value = line[len(marker):].strip()
                    break
            # Keep the preferred reading before slash-separated alternatives.
            value = value.split("/", 1)[0].strip()
            if value and value not in entry[kind]:
                entry[kind].append(value)
    return entries


def split_ipa_values(value: object) -> list[str]:
    if pd.isna(value):
        return []
    return [part.strip() for part in re.split(r"[,()/]", str(value))
            if part.strip() and part.strip() != "#"]


def build_ipa_database(path: Path) -> dict[str, object]:
    """Convert the IPA matrix into longest-match lookup tables per language."""
    frame = pd.read_excel(path, sheet_name=IPA_SHEET, header=None)
    header = [str(value).strip() for value in frame.iloc[HEADER_ROW]]
    try:
        first_tailo_column = header.index("TL")
    except ValueError as error:
        raise ValueError(f"{IPA_SHEET} 工作表第 {HEADER_ROW + 1} 列找不到 TL 標頭") from error

    languages = {language: {"combinations": {}} for language in LANG_ROW_MAP.values()}
    for column in range(first_tailo_column, frame.shape[1]):
        column_ipas: dict[str, list[str]] = {}
        for row, language in LANG_ROW_MAP.items():
            column_ipas[language] = [""] if column == first_tailo_column else split_ipa_values(frame.iloc[row, column])

        for row in range(FIRST_VOWEL_ROW, len(frame)):
            vowel_value = frame.iloc[row, 0]
            if pd.isna(vowel_value):
                continue
            vowel_text = str(vowel_value).strip()
            vowels = [""] if "輔音後無元音" in vowel_text else [part.strip() for part in vowel_text.split(",") if part.strip()]
            tailo_value = frame.iloc[row, column]
            if pd.isna(tailo_value) or not str(tailo_value).strip():
                continue
            # The first value is the website's suggested/default reading.
            tailo = str(tailo_value).split(",", 1)[0].split("(", 1)[0].strip()
            for language, consonants in column_ipas.items():
                combinations = languages[language]["combinations"]
                for consonant in consonants:
                    for vowel in vowels:
                        # 「拼字」是資料表的特殊標記：ə、ɚ、ɜ、ɝ 不轉寫，
                        # 而是直接保留原 IPA 字元。
                        combinations[consonant + vowel] = vowel if tailo == "拼字" else tailo

    return {IPA_SHEET: {"languages": languages}}


def main() -> None:
    for path in (HANJI_SOURCE, IPA_SOURCE):
        if not path.exists():
            raise FileNotFoundError(f"找不到來源檔：{path}")

    database = {
        "hanji": build_hanji_database(HANJI_SOURCE),
        "ipa": build_ipa_database(IPA_SOURCE),
    }
    OUTPUT.write_text(
        "window.TAILO_DB = " + json.dumps(database, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )
    ipa_counts = {lang: len(data["combinations"])
                  for lang, data in database["ipa"][IPA_SHEET]["languages"].items()}
    print(f"已寫入 {OUTPUT.name}")
    print(f"漢字條目：{len(database['hanji'])}")
    print("IPA 規則：" + ", ".join(f"{lang} {count}" for lang, count in ipa_counts.items()))


if __name__ == "__main__":
    main()
