Developer Guide

# AWS Lambda

Copyright © 2024 Amazon Web Services, Inc. and/or its affiliates. All rights reserved.


**AWS Lambda: Developer Guide**

Copyright © 2024 Amazon Web Services, Inc. and/or its affiliates. All rights reserved.

Amazon's trademarks and trade dress may not be used in connection with any product or service
that is not Amazon's, in any manner that is likely to cause confusion among customers, or in any
manner that disparages or discredits Amazon. All other trademarks not owned by Amazon are
the property of their respective owners, who may or may not be affiliated with, connected to, or
sponsored by Amazon.

**Document history...................................................................................................................... 2400**
Earlier updates....................................................................................................................................... 2423

```
xxxi
```

## What is AWS Lambda?....................................................................................................................

You can use AWS Lambda to run code without provisioning or managing servers.

Lambda runs your code on a high-availability compute infrastructure and performs all of the
administration of the compute resources, including server and operating system maintenance,
capacity provisioning and automatic scaling, and logging. With Lambda, all you need to do is
supply your code in one of the language runtimes that Lambda supports.

You organize your code into Lambda functions. The Lambda service runs your function only when
needed and scales automatically. You only pay for the compute time that you consume—there is
no charge when your code is not running. For more information, see AWS Lambda Pricing.

```
Tip
To learn how to build serverless solutions , check out the Serverless Developer Guide.
```
### When to use Lambda..................................................................................................................................

Lambda is an ideal compute service for application scenarios that need to scale up rapidly, and
scale down to zero when not in demand. For example, you can use Lambda for:

- **File processing:** Use Amazon Simple Storage Service (Amazon S3) to trigger Lambda data
    processing in real time after an upload.
- **Stream processing:** Use Lambda and Amazon Kinesis to process real-time streaming data for
    application activity tracking, transaction order processing, clickstream analysis, data cleansing,
    log filtering, indexing, social media analysis, Internet of Things (IoT) device data telemetry, and
    metering.
- **Web applications:** Combine Lambda with other AWS services to build powerful web applications
    that automatically scale up and down and run in a highly available configuration across multiple
    data centers.
- **IoT backends:** Build serverless backends using Lambda to handle web, mobile, IoT, and third-
    party API requests.
- **Mobile backends:** Build backends using Lambda and Amazon API Gateway to authenticate and
    process API requests. Use AWS Amplify to easily integrate with your iOS, Android, Web, and
    React Native frontends.

When to use Lambda 1


When using Lambda, you are responsible only for your code. Lambda manages the compute fleet
that offers a balance of memory, CPU, network, and other resources to run your code. Because
Lambda manages these resources, you cannot log in to compute instances or customize the
operating system on provided runtimes. Lambda performs operational and administrative activities
on your behalf, including managing capacity, monitoring, and logging your Lambda functions.

### Key features...................................................................................................................................................

The following key features help you develop Lambda applications that are scalable, secure, and
easily extensible:

**Environment variables**

```
Use environment variables to adjust your function's behavior without updating code.
```
**Versions**

```
Manage the deployment of your functions with versions, so that, for example, a new function
can be used for beta testing without affecting users of the stable production version.
```
**Container images**

```
Create a container image for a Lambda function by using an AWS provided base image or an
alternative base image so that you can reuse your existing container tooling or deploy larger
workloads that rely on sizable dependencies, such as machine learning.
```
**Layers**

```
Package libraries and other dependencies to reduce the size of deployment archives and makes
it faster to deploy your code.
```
**Lambda extensions**

```
Augment your Lambda functions with tools for monitoring, observability, security, and
governance.
```
**Function URLs**

```
Add a dedicated HTTP(S) endpoint to your Lambda function.
```
**Response streaming**

```
Configure your Lambda function URLs to stream response payloads back to clients from Node.js
functions, to improve time to first byte (TTFB) performance or to return larger payloads.
```
Key features 2


**Concurrency and scaling controls**

```
Apply fine-grained control over the scaling and responsiveness of your production applications.
```
**Code signing**

```
Verify that only approved developers publish unaltered, trusted code in your Lambda functions
```
**Private networking**

```
Create a private network for resources such as databases, cache instances, or internal services.
```
**File system access**

```
Configure a function to mount an Amazon Elastic File System (Amazon EFS) to a local
directory, so that your function code can access and modify shared resources safely and at high
concurrency.
```
**Lambda SnapStart for Java**