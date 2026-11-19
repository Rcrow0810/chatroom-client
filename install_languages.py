# install_languages.py
# ---------------------------------------------------------
# One-time setup for OFFLINE translation. This is the only step that needs internet;
# afterwards the chat translates with no connection at all.
#
#   pip install argostranslate langdetect
#   python3 install_languages.py es fr de          install English<->Spanish, French, German
#   python3 install_languages.py --list            show every language available to download
#   python3 install_languages.py --installed       show what's installed now
#   python3 install_languages.py --file es_en.argosmodel   install a pack you downloaded yourself
#
# No internet on the chat computer at all? Run this on any computer that has it, then copy the
# folder it prints at the end (Argos's data folder) to the same place on the other computer, or
# download the .argosmodel files from https://www.argosopentech.com/argospm/index/ and use --file.
#
# Each language adds about 50-100 MB. Languages other than English go through English, so
# installing "es" and "fr" also lets Spanish<->French work.
# ---------------------------------------------------------

import sys

try:
    import argostranslate.package as package
    import argostranslate.translate as translate
except ImportError:
    sys.exit("argostranslate isn't installed.  Run:  pip install argostranslate langdetect")

DEFAULT_LANGUAGES = ["es", "fr", "de", "pt"]
ALIASES = {"iw": "he", "zh-cn": "zh", "zh-tw": "zh"}


def show_installed():
    codes = sorted(lang.code for lang in translate.get_installed_languages())
    print("Installed languages:", ", ".join(codes) if codes else "(none yet)")


def main(args):
    if "--installed" in args:
        show_installed()
        return 0
    if "--file" in args:
        for path in args[args.index("--file") + 1:]:
            package.install_from_path(path)
            print("Installed", path)
        show_installed()
        return 0

    print("Getting the list of language packs (needs internet)...")
    package.update_package_index()
    available = package.get_available_packages()

    if "--list" in args:
        pairs = sorted({(p.from_code, p.to_code) for p in available})
        print("Available:", ", ".join(sorted({c for pair in pairs for c in pair})))
        return 0

    wanted = [ALIASES.get(a.lower(), a.lower()) for a in args if not a.startswith("--")] or DEFAULT_LANGUAGES
    failures = 0
    for code in wanted:
        if code == "en":
            continue
        for src, dst in ((code, "en"), ("en", code)):
            pack = next((p for p in available if p.from_code == src and p.to_code == dst), None)
            if pack is None:
                print(f"  {src} -> {dst}: no pack exists for this pair (try --list)")
                failures += 1
                continue
            print(f"  downloading {src} -> {dst} ...")
            package.install_from_path(pack.download())
            print(f"  installed   {src} -> {dst}")
    show_installed()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
