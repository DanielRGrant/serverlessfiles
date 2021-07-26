var AWS = require('aws-sdk');
AWS.config.update({region: 'us-east-1'});
s3 = new AWS.S3({apiVersion: '2006-03-01'});

const UploadData = (bucket, file) => {
    // call S3 to retrieve upload file to specified bucket
    var uploadParams = {Bucket: bucket, Key: '', Body: ""};

    // Configure the file stream and obtain the upload parameters
    var fs = require('fs');
    var fileStream = fs.createReadStream(file);
    fileStream.on('error', function(err) {
    console.log('File Error', err);
    });
    uploadParams.Body = fileStream;
    var path = require('path');
    uploadParams.Key = path.basename(file);

    // call S3 to retrieve upload file to specified bucket
    s3.upload (uploadParams, function (err, data) {
        if (err) {
            console.log("Error", err);
        } if (data) {
            console.log('Upload success');
        }
    });
};
const stack = require(process.argv[2])
const bucket = stack[process.argv[3]]
const file = process.argv[4]

UploadData ( bucket, file )

