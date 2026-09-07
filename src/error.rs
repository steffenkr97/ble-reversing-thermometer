use thiserror::Error;

#[derive(Debug, Error)]
pub enum Error {
    #[error("leerer FFF5-Write")]
    EmptyWrite,
    #[error("Blacklist-Opcode 0x{0:02X} — nicht senden")]
    BlacklistOpcode(u8),
    #[error("unbeobachteter Opcode 0x{0:02X}")]
    UnknownOpcode(u8),
    #[error("07-Write muss 6 Byte sein, nicht {0}")]
    HistoryWriteLen(usize),
    #[error("07-Write Bytes 3–4 müssen 00 00 sein")]
    HistoryWritePadding,
    #[error("07-Write count nur 01 oder 03, nicht {0}")]
    HistoryWriteCount(u8),
    #[error("Opcode 0x{0:02X} nur als 1-Byte-Write")]
    SingleByteWrite(u8),
    #[error("sample_count muss >= 0 sein")]
    NegativeSampleCount,
    #[error("interval_sec muss > 0 sein")]
    NonPositiveInterval,
    #[error("leerer Zeitstempel")]
    EmptyTimestamp,
    #[error("Zeitstempel: {0}")]
    Timestamp(String),
    #[error("{0}")]
    Message(String),
    #[error(transparent)]
    Io(#[from] std::io::Error),
    #[error(transparent)]
    Json(#[from] serde_json::Error),
    #[error(transparent)]
    Csv(#[from] csv::Error),
}

pub type Result<T> = std::result::Result<T, Error>;
