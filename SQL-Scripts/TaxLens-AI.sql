-- TaxLens-AI — optional SQL Server schema for audit metadata (on-premise).
-- Application default uses JSONL under data/audit_logs/; use this if you want relational storage.

CREATE DATABASE TaxLens_AI;
GO

USE TaxLens_AI;
GO

CREATE TABLE AuditEvent (
    EventId UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    TsUtc DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    Actor NVARCHAR(256) NOT NULL,
    Action NVARCHAR(256) NOT NULL,
    ActionDetail NVARCHAR(MAX) NULL,
    RequiresHumanReview BIT NOT NULL DEFAULT 1,
    Confidence FLOAT NULL
);

CREATE TABLE RetrievedDocumentRef (
    Id BIGINT IDENTITY(1,1) PRIMARY KEY,
    EventId UNIQUEIDENTIFIER NOT NULL FOREIGN KEY REFERENCES AuditEvent(EventId),
    DocRef NVARCHAR(512) NOT NULL
);

CREATE INDEX IX_AuditEvent_Ts ON AuditEvent(TsUtc DESC);
