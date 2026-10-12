-- Procedural statements that sqlglot's parser rejects or silently rewrites.
-- No semicolons on purpose: T-SQL does not require them.
CREATE PROCEDURE dbo.usp_CloseStaleOrders
    @Cutoff DATE = NULL,
    @MaxRows INT = 500,
    @Closed INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON
    IF @Cutoff IS NULL SET @Cutoff = DATEADD(day, -90, GETDATE())
    IF @MaxRows < 1 RETURN -1

    DECLARE @OrderId INT, @Attempts INT = 0
    DECLARE stale CURSOR LOCAL FAST_FORWARD FOR
        SELECT TOP (@MaxRows) OrderId FROM dbo.Orders WHERE Status = 'OPEN' AND OrderDate < @Cutoff

    OPEN stale
    FETCH NEXT FROM stale INTO @OrderId
    WHILE @@FETCH_STATUS = 0
    BEGIN
        BEGIN TRY
            BEGIN TRANSACTION
            UPDATE dbo.Orders SET Status = 'CLOSED', ClosedAt = SYSDATETIME() WHERE OrderId = @OrderId
            INSERT INTO dbo.OrderEvents (OrderId, EventType) VALUES (@OrderId, 'AUTO_CLOSE')
            COMMIT TRANSACTION
            SET @Closed = ISNULL(@Closed, 0) + 1
        END TRY
        BEGIN CATCH
            IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION
            SET @Attempts += 1
            PRINT 'Could not close order ' + CAST(@OrderId AS VARCHAR(20)) + ': ' + ERROR_MESSAGE()
            IF @Attempts >= 3
            BEGIN
                CLOSE stale
                DEALLOCATE stale
                RAISERROR('Too many failures while closing orders before %s', 16, 1, @Cutoff)
                RETURN -2
            END
        END CATCH
        FETCH NEXT FROM stale INTO @OrderId
    END
    CLOSE stale
    DEALLOCATE stale

    IF EXISTS (SELECT 1 FROM dbo.Orders WHERE Status = 'OPEN' AND OrderDate < @Cutoff)
        PRINT 'Stale orders remain'
    ELSE
    BEGIN
        PRINT 'All stale orders closed'
        EXEC dbo.usp_LogEvent @Source = 'usp_CloseStaleOrders', @Rows = @Closed
    END

    IF @Closed > 10000 THROW 50001, 'Unexpectedly many orders closed', 1
    RETURN 0
END
GO
