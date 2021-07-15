'use strict';

const AWS = require('aws-sdk');
const s3 = new AWS.S3({signatureVersion: 'v4'});
const bucket = process.env.BUCKET

exports.handler = (event, context, callback) => {
  if (!bucket) {
    callback(new Error(`S3 bucket not set`));
  }
  console.log(event)

  //Get metadataN
 // const tmpMetadata = JSON.stringify(event["queryStringParameters"])
  //const metadata = {"x-amz-meta-data": "poo"}
  const rand = Math.floor(Math.random() * 100000000000000)
  const key = rand.toString();
  if (!key) {
    callback(new Error('S3 object key missing'));
    return;
  }
  JSON.stringify()
  const params = {
      'Bucket': bucket, 
      'Key': key,
      'Metadata': event
  };

  s3.getSignedUrl('putObject', params, (error, url) => {
    if (error) {
      console.log(error)
      callback(error);
    } else {
      console.log(url)
        const response = {
            statusCode: 200,
            body: JSON.stringify(
                {"url": url,
                "key": key
            }),
        };
        callback(null, response);
    }
  });
};

