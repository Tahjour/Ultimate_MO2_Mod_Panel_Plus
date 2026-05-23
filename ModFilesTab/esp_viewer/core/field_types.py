# Сигнатуры подзаписей, которые ВСЕГДА содержат ровно один FormID (4 байта)
FORMID_FIELD_SIGNATURES: frozenset[str] = frozenset({
    "INAM", "TNAM", "BNAM", "CNAM", "DNAM", "ENAM",
    "GNAM", "HNAM", "KNAM", "LNAM", "MNAM", "NNAM",
    "ONAM", "PNAM", "QNAM", "RNAM", "SNAM", "UNAM",
    "VNAM", "WNAM", "XNAM", "YNAM", "ZNAM",
    "ANAM", "SCRI", "NAME", "XOWN", "XLCN",
    "XEZN", "XLRL", "XMRK",
})

# Сигнатуры, которые НИКОГДА не являются FormID (даже при размере 4)
NON_FORMID_SIGNATURES: frozenset[str] = frozenset({
    "DATA", "XSCL", "FNAM", "HEDR", "INTV", "INCC",
    "XCLW", "XCLR", "XCMT", "XRNK",
})

# Сигнатуры, содержащие массивы FormID (кратно 4 байтам)
FORMID_ARRAY_SIGNATURES: frozenset[str] = frozenset({"KWDA", "CNTO", "CTDA"})
