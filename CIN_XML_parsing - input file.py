import pyspark
import os
import sys
from pyspark.sql.functions import *
import pyspark.sql.functions as F
import pyspark.sql.types as T
from pyspark.sql import Column
from os import path
sys.path.append(path.abspath(os.path.join(os.path.dirname(__file__), '../')))
from bin.init import *
from datetime import datetime
import xml.etree.ElementTree as ET
from pyspark.sql import SparkSession
from pyspark.sql.types import (StructType, StructField, StringType,
    FloatType, DateType, LongType)
from pyspark.sql import *
from pyspark.sql.functions import *
import os


file_to_parse = "s3://" + bucket + unprocessed_tracelink

file_rdd = spark.read.text("s3://us-e1-odp-rs-dev-datalake/inbound/test/20201119155306_DispositionAssigned-0300239550049-W04696-20201119-074928-578.xml", wholetext=True).rdd


COL_NAMES_BODY = ['ns1:ItemCode', 'ns1:InternalMaterialCode', 'ns1:LotNumber', 'ns1:ExpirationDate', 'ns1:EventDateTime', 'ns0:CommissionEvent']
ELEMENTS_TO_EXTRAT_BODY = [c for c in COL_NAMES_BODY]


def parse_xml_body(rdd):
    results = []
    InternalMaterialCode=""
    LotNumber=""
    ExpirationDate=""
    ItemCode=""
    root = ET.fromstring(rdd[0])
    ns0map = {"ns0":"urn:tracelink:mapper:sl:serial_number_exchange"}
    innerroot1 = root.find('ns0:MessageBody', ns0map)

    childlist = innerroot1.getchildren()
    for c in childlist:
        if "EventSummary" in c.tag:
            ns0map = {"ns0":"urn:tracelink:mapper:sl:serial_number_exchange"}
            innerroot2 = innerroot1.find('ns0:EventSummary', ns0map)
            ns1map = {"ns1":"urn:tracelink:mapper:sl:commontypes"}
            InternalMaterialCode = innerroot2.find('ns1:InternalMaterialCode', ns1map).text
            LotNumber = innerroot2.find('ns1:LotNumber', ns1map).text


    for b in innerroot1.findall('ns0:CommissionEvent', ns0map):
        rec = []
        for e in ELEMENTS_TO_EXTRAT_BODY:
            if e == 'ns1:ItemCode':
                ns0map = {"ns0":"urn:tracelink:mapper:sl:serial_number_exchange"}
                iroot1 = b.find('ns0:CommissionCommonAttributes', ns0map)
                iroot2 = iroot1.find('ns0:ItemDetail', ns0map)
                ns1map = {"ns1":"urn:tracelink:mapper:sl:commontypes"}
                if iroot2.find('ns1:ItemCode', ns1map) is None:
                    rec.append(None)
                    continue
                else:
                    value = iroot2.find('ns1:ItemCode', ns1map).text
            if e == 'ns1:InternalMaterialCode':
                if InternalMaterialCode == "":
                    ns0map = {"ns0":"urn:tracelink:mapper:sl:serial_number_exchange"}
                    iroot3 = b.find('ns0:CommissionCommonAttributes', ns0map)
                    iroot4 = iroot3.find('ns0:ItemDetail', ns0map)
                    ns1map = {"ns1":"urn:tracelink:mapper:sl:commontypes"}
                    if iroot4.find('ns1:InternalMaterialCode', ns1map) is None:
                        rec.append(None)
                        continue
                    else:
                        value = iroot4.find('ns1:InternalMaterialCode', ns1map).text
                else:
                    value = InternalMaterialCode
            if e == 'ns1:LotNumber':
                if LotNumber == "":
                    ns0map = {"ns0":"urn:tracelink:mapper:sl:serial_number_exchange"}
                    iroot5 = b.find('ns0:CommissionCommonAttributes', ns0map)
                    iroot6 = iroot5.find('ns0:ItemDetail', ns0map)
                    ns1map = {"ns1":"urn:tracelink:mapper:sl:commontypes"}
                    if iroot6.find('ns1:LotNumber', ns1map) is None:
                        rec.append(None)
                        continue
                    else:
                        value = iroot6.find('ns1:LotNumber', ns1map).text
                else:
                    value = LotNumber
            if e == 'ns1:ExpirationDate':
                ns0map = {"ns0":"urn:tracelink:mapper:sl:serial_number_exchange"}
                iroot7 = b.find('ns0:CommissionCommonAttributes', ns0map)
                iroot8 = iroot7.find('ns0:ItemDetail', ns0map)
                ns1map = {"ns1":"urn:tracelink:mapper:sl:commontypes"}
                if iroot8.find('ns1:ExpirationDate', ns1map) is None:
                    rec.append(None)
                    continue
                else:
                    value = iroot8.find('ns1:ExpirationDate', ns1map).text
            if e == 'ns1:EventDateTime':
                ns0map = {"ns0":"urn:tracelink:mapper:sl:serial_number_exchange"}
                iroot7 = b.find('ns0:CommissionEventDetail', ns0map)
                ns1map = {"ns1":"urn:tracelink:mapper:sl:commontypes"}
                if iroot7.find('ns1:EventDateTime', ns1map) is None:
                    rec.append(None)
                    continue
                else:
                    sub_value_eventtime = iroot7.find('ns1:EventDateTime', ns1map).text
                    value = sub_value_eventtime.split('T')[0]
            if e == 'ns0:CommissionEvent':
                eventlist = innerroot1.getchildren()
                sub_value = eventlist[1].tag.split('}')[1]
                value = sub_value.replace("Event","")
            rec.append(value)
        results.append(rec)
    return results

records_rdd_body = file_rdd.flatMap(parse_xml_body)

def set_schema_body():
    schema_list = []
    for c in COL_NAMES_BODY:
        schema_list.append(StructField(c, StringType(), True))
    return StructType(schema_list)


my_schema_body = set_schema_body()
body_df = records_rdd_body.toDF(my_schema_body)
body_df.createOrReplaceTempView("body_df_schema")
final_df_2 = spark.sql('select CAST(`ns1:ItemCode` AS STRING) as GTIN, CAST(`ns1:InternalMaterialCode` AS STRING) as material, CAST(`ns1:LotNumber` AS STRING) as batch, CAST(`ns1:ExpirationDate` AS STRING) as expiration_date, CAST(`ns1:EventDateTime` AS STRING) as event_date, CAST(`ns0:CommissionEvent` AS STRING) as event_type from body_df_schema')
final_df_2 = final_df_2.distinct()



COL_NAMES_HEADER = ['ns1:FileSenderNumber']
ELEMENTS_TO_EXTRAT_HEADER = [c for c in COL_NAMES_HEADER]

def parse_xml_header(rdd):
    results = []
    root = ET.fromstring(rdd[0])
    ns0map = {"ns0":"urn:tracelink:mapper:sl:serial_number_exchange"}
    for b in root.findall('ns0:ControlFileHeader', ns0map):
        rec = []
        for e in ELEMENTS_TO_EXTRAT_HEADER:
            if e == 'ns1:FileSenderNumber':
                ns1map = {"ns1":"urn:tracelink:mapper:sl:commontypes"}
                value = b.find('ns1:FileSenderNumber', ns1map).text
                rec.append(value)
        results.append(rec)
    return results

records_rdd_header = file_rdd.flatMap(parse_xml_header)

def set_schema_header():
    schema_list = []
    for c in COL_NAMES_HEADER:
        schema_list.append(StructField(c, StringType(), True))
    return StructType(schema_list)

my_schema_header = set_schema_header()
header_df = records_rdd_header.toDF(my_schema_header)
header_df.createOrReplaceTempView("header_df_schema")
final_df_1 = spark.sql('select CAST(`ns1:FileSenderNumber` AS STRING) as GLN from header_df_schema')
final_df_1 = final_df_1.distinct()




file_name = '20201119155306_DispositionAssigned-0300239550049-W04696-20201119-074928-578.xml'
tracelink_id = file_name.split('_')[0]
filename = file_name


gln_value = str(final_df_1.rdd.map(lambda x: x.GLN).collect()[0])

final_df = final_df_2.withColumn('gln', lit(gln_value)).withColumn('file_name', lit(file_name)).withColumn('tracelink_id', lit(tracelink_id)).filter(final_df_2.GTIN.isNotNull())




df_col_renamed = final_df.withColumnRenamed("expiration_date","expiration_date").withColumnRenamed("eventType","event_type").withColumnRenamed("processDate","processed_date")

df_tostore_s3 = df_col_renamed.select("gtin", "material", "batch", "expiration_date", "file_name", "tracelink_id", "processed_date", "event_type", "gln")

df_tostore_s3.coalesce(1).write.csv("s3://us-e1-odp-rs-dev-datalake/inbound/test/CIN_tracelink_metadata")



os.system("aws s3 sync s3://us-e1-odp-rs-dev-datalake/inbound/test/CIN_tracelink_metadata/ s3://us-e1-odp-rs-dev-datalake/inbound/test/ --include '*.csv'")
os.system("aws s3 rm s3://us-e1-odp-rs-dev-datalake/inbound/test/CIN_tracelink_metadata --recursive")