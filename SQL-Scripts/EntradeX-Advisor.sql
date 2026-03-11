CREATE DATABASE EntradeX_Advisor;
GO

USE EntradeX_Advisor
GO

--Bang luu du lieu thi truong moi thang, can nhap du lieu vao
CREATE TABLE Market_Condition (
	LogID INT IDENTITY (1,1) PRIMARY KEY,
	LogDate DATE DEFAULT GETDATE(),
	PERatio FLOAT NOT NULL,
	InterestRate FLOAT NOT NULL
);

--Bang luu lai loi khuyen cua Bot
CREATE TABLE Bot_Advice (
	RecID INT IDENTITY (1,1) PRIMARY KEY,
	LogID INT FOREIGN KEY REFERENCES Market_Condition(LogID),
	Suggested_Action NVARCHAR(100),
	Is_Executed BIT DEFAULT 0
);