var AWS = require('aws-sdk');

AWS.config.update({region: 'us-east-1'});
dynamodb = new AWS.DynamoDB();

const UploadData = (table, json) => {
    var items = json.map(inItem => {
        var outItem = {
            "PutRequest": {
                "Item": AWS.DynamoDB.Converter.marshall(inItem)
            }
        }
        return outItem
    });
//    console.log(JSON.stringify(items))
    var params = {
        RequestItems: {
            [table]: items
        }
    };
    dynamodb.batchWriteItem(params, function (err, data) {
        if (err) console.log(err, err.stack); // an error occurred
        else console.log("success");           // successful response
    });
};

//const stack = require("./build/dynamodb_stack.json")
//const table = stack[process.argv[2]]
const table = 'sls-class-db'
const json = require(process.argv[3])


UploadData ( table, json )
