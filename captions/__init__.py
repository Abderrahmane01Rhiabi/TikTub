"""The shared caption library: every caption style of the app in one catalogue, usable by every space.

    core      fonts (Latin + Arabic), words measured with the real shaping (raqm), the context a style is drawn in
              (zone, position, language, strong words, channel colour, faces), the common settings
    styles    the catalogue: the new styles (lab montage_test/alex, catalogue of 2026-11-03) and the spaces' own
              (Génération, Montage auto — delegated to their code, identical; Adaptation's shown in the gallery)
    render    a style + words -> .ass and its extras (blend modes, perspective, emojis, a click, text behind the
              person), the ffmpeg filters that burn them, the gallery's previews, faces (YuNet), person masks (SAM)

Arabic everywhere: Tajawal, encoding -1 (right-to-left base) and libass's complex shaping (without it the final forms
of ه / ة came out as boxes).
"""
