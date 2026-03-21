DELETE FROM Bot_Advice;
DELETE FROM Market_Condition;

DBCC CHECKIDENT ('Bot_Advice', RESEED, 0);
DBCC CHECKIDENT ('Market_Condition', RESEED, 0);