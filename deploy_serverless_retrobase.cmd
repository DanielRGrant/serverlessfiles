sls deploy --config ServerlessRetrobaseQueryApi.yml --stage dev & sls deploy --config ServerlessRetrobaseDynamo.yml --stage dev & sls deploy --config ServerlessRetrobaseLayers.yml --stage dev & sls deploy --config ServerlessRetrobaseFunctions.yml --stage dev & node ServerlessRetrobaseUploadData.js S3UploadQueryData ./artifacts/smaller_ervdata.json & node ServerlessRetrobaseUploadData.js S3UploadUniprotData ./artifacts/uniprotData.json