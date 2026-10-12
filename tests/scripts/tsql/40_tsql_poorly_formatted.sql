select   c.customerid,c.name ,(select count(*) from dbo.orders o where o.customerid=c.customerid and o.status in('OPEN','HELD'))open_orders,case when c.creditlimit>10000 then'HIGH'when c.creditlimit>1000 then'MID'else'LOW'end tier from dbo.customers c left join dbo.regions r on r.regionid=c.regionid where c.active=1 and(r.name like'North%'or r.name is null)group by c.customerid,c.name,c.creditlimit having count(*)>0 order by 3 desc,c.name
	INSERT	INTO dbo.audit(who,what)VALUES(SUSER_SNAME(),'report run')
UPDATE c SET c.lastseen=GETDATE()FROM dbo.customers c WHERE c.customerid IN(SELECT customerid FROM dbo.orders WHERE orderdate>DATEADD(dd,-7,GETDATE()))


DELETE FROM dbo.staging WHERE loaded<DATEADD(mm,-1,GETDATE());;
