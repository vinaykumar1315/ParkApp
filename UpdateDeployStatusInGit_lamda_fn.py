import json
import os
import boto3
import zipfile
import tempfile
import traceback
import botocore
from botocore.vendored import requests
from boto3.session import Session
code_pipeline = boto3.client('codepipeline')

def get_pipeline_name(job_id):
    '''
    Query the codepipeline state and get the name
    '''
    client = boto3.client('codepipeline')
    response = client.get_job_details(jobId= job_id)
    return response['jobDetails']['data']['pipelineContext']['pipelineName']


def get_deployment_id(pipeline_name):
    '''
    Query the codepipeline state and get the name of the latest deploymentId
    '''
    client = boto3.client('codepipeline')
    response = client.get_pipeline_state(name=pipeline_name)
    return response['stageStates'][1]['actionStates'][0]['latestExecution']['externalExecutionId']

def get_deployment_status(id='None'):
    client = boto3.client('codedeploy')
    response = client.batch_get_deployments(deploymentIds=[id])
    return response['deploymentsInfo'][0]['status']


def setup_s3_client(job_data):
    """Creates an S3 client

    Uses the credentials passed in the event by CodePipeline. These
    credentials can be used to access the artifact bucket.

    Args:
        job_data: The job data structure

    Returns:
        An S3 client with the appropriate credentials

    """
    key_id = job_data['artifactCredentials']['accessKeyId']
    key_secret = job_data['artifactCredentials']['secretAccessKey']
    session_token = job_data['artifactCredentials']['sessionToken']
    
    # key_id = 'ASIATNTI6JAPU2IF7SWZ'
    # key_secret = 'SstDr23pB4873C+8isY7QJqLI7BSYAmOXB8/tyTz'
    # session_token = 'AgoGb3JpZ2luEAkaCXVzLWVhc3QtMSKAAjNm7SUo2fdvdAHFZyTZntDYvPNTdouGZ2zdMW99RavckQ0h7NMIDQ8ae+3PGytWTYcQXK3JAq1jcPGW1VtE+kOqkG/0GCOC4Rtj9PcdigT9vgMQov3qzPxQHkUk9q+fYpSoYwETv6bvc6j/SiZ8zdCOyVUCzXsGZTWNENODMrOV3F9CcWd74MweQg0TbP+5J0jEzEfIGMXcHAS84EJvmkti3iiYlnvF1gYilCFL4HkqtJo7Ml84Kr1nc/hmJJ7jFNCYMr7CjQG5Php9datNxy3jX1LGwdoKnT858aclMzQ35YILdbSL/2LxWC+iMqQwPTIV4ZMAGbPub5vPealBDWsqgwUI3v//////////ARABGgwyMzUzNjk1NDc4MDciDC0H/R6oHIwcn0YmQSrXBAR1srDQCx/oq2ju3lKSCE/CvLHPwPpo8ZKJXbgVp/bNJaRqi3x7ivoBOE/yIRBJSOmzM2SbBfIMYr0eOOiGeW058vlj75gLNhGzG6DDxroU+mJ/y/Dioaaz2YHIIlOSiz21BgOSy6ImnxY7X4Yv4+9GkHi/dMMiZJXyqH4SAvWlsaFXOJZmtVeate4NdHA/ZPN3Mh0PTfSA0iGNOfFkhLj4ZPS17M9ODijaJJuE0vX7+HcaS67q38+YEmkbZL6OAQb8eTitnVBDiNipIK7u3EwFmZCluz/Jn/MJ+zgmUiKOoHiEM4WpL7e+LAm7Q9gxiyi0/r1Y4cGaPDFIgafZ4qlQ72vyROreXMD5rWLKpgFL61hEYM7UkOBmdRxO6sg6W4bpv145oCvbAd29BhUXFtD3A1w2EdrVjKx43N3fhqulAGfdsATAKqbsvDnJBpMJ9w87XXPIfaXk3RJ9zKaR15iFgjPv7LSNvOxnE900mFQ9M4LwDp+jCMqyd/slo2WIcTKf5GHeFkqOrbtu+YRS+9fVTh/fYpobTgYAGIOY9mi+T/96A8rnmqiX6UROAJJwFsqwZ2JzhsNQWr0wmtJecz26nHyDIDqZWpz+JjMGn5mcKdm1UnTCesu+CEuqjk0X4VNyZbWHYHIZF6qUKduG8P9TkjCpVusqQoNf2r4DaNxuGINlf0LJW5AzCupuCea/dCBIT4rgn5RuphFpiuwFta/EGE/qU2UDwE5Sf4jS6De2+vDJ7T827iNmJHNUGUtN9Ang+SmyEwstk0VRPzulR1KU2j73Lf6zMMeLv+EF'

    session = Session(aws_access_key_id=key_id,
                      aws_secret_access_key=key_secret,
                      aws_session_token=session_token)
    return session.client('s3', config=botocore.client.Config(signature_version='s3v4'))
    
def get_data_from_s3(s3, artifact):
    tmp_file = tempfile.NamedTemporaryFile()
    bucket = artifact['location']['s3Location']['bucketName']
    key = artifact['location']['s3Location']['objectKey']
    file_in_zip = os.environ['CODE_BUILD_DATA'] # Will be passed as an Environment Variable to get the GitBranch and CommitID details
    with tempfile.NamedTemporaryFile() as tmp_file:
        s3.download_file(bucket, key, tmp_file.name)
        with zipfile.ZipFile(tmp_file.name, 'r') as zip:
            return zip.read(file_in_zip)

def post_status_on_pr(data, deployment_status):
    headers = {
        'Authorization': 'token '+os.environ['GIT_ACCESS_TOKEN'],
        'Content-Type': 'application/json'
    }
    input_data = data.split(" ")
    CODEBUILD_SOURCE_REPO_URL = input_data[0]
    owner, repo = CODEBUILD_SOURCE_REPO_URL.split("/")[-2:]
    repo = repo.split(".")[0]
    CODEBUILD_SOURCE_VERSION = input_data[1].split("\n")[0]
    commit_id = ''
    if '/' in CODEBUILD_SOURCE_VERSION:
        pr_num = CODEBUILD_SOURCE_VERSION.split("/")[1]
        GET_COMMENTS_ON_PR = "https://api.github.com/repos/"+owner+"/"+repo+"/pulls/"+pr_num+"/commits"
        print GET_COMMENTS_ON_PR
        r = requests.get(url=GET_COMMENTS_ON_PR,headers=headers, verify=True).json()
        commit_id = r[-1]['sha'] # latest commit on a PR 
    else:
        commit_id = CODEBUILD_SOURCE_VERSION.split("\n")[0]
    
    print('CODEBUILD_SOURCE_VERSION', CODEBUILD_SOURCE_VERSION, commit_id)
    GITHUB_URL = "https://api.github.com/repos/"+owner+"/"+repo+"/statuses/"+commit_id
    state = 'failure'
    description = 'AWS Code Deploy failed!!!!!'
    context = 'AWS Code Deploy failed'
    print("Deployment status ", deployment_status)
    if deployment_status == 'Succeeded':
        state = "success"
        description = "AWS Code Deploy success!!!!!"
        context = "AWS Code Deploy success"
    data ={
      "state": state,
      "target_url": "https://example.com/build/status",
      "description": description,
      "context": context
    }


   
    r = requests.post(url=GITHUB_URL, data=json.dumps(data), headers=headers).json()
    print r 
    
def put_job_failure(job, message):
    """Notify CodePipeline of a failed job

    Args:
        job: The CodePipeline job ID
        message: A message to be logged relating to the job status

    Raises:
        Exception: Any exception thrown by .put_job_failure_result()

    """
    print('Putting job failure')
    print(message)
    code_pipeline.put_job_failure_result(jobId=job, failureDetails={'message': message, 'type': 'JobFailed'})
    
def put_job_success(job, message):
    """Notify CodePipeline of a successful job

    Args:
        job: The CodePipeline job ID
        message: A message to be logged relating to the job status

    Raises:
        Exception: Any exception thrown by .put_job_success_result()

    """
    print('Putting job success')
    print(message)
    code_pipeline.put_job_success_result(jobId=job)

def lambda_handler(event, context):
    # Extract the Job ID
    job_id = event['CodePipeline.job']['id']
    pipeline_name = get_pipeline_name(job_id)
    deployment_id = get_deployment_id(pipeline_name)
    deployment_status = get_deployment_status(id=str(deployment_id))
    print("Event Data", event)
    try:
        
        # Extract the Job Data
        job_data = event['CodePipeline.job']['data']

        artifacts = job_data['inputArtifacts']
        print("Artifacts ", artifacts)
        # Get S3 client to access artifact with
        s3 = setup_s3_client(job_data)
        # Get the JSON template file out of the artifact
        s3_data = get_data_from_s3(s3, artifacts[0])
        #Process details from the file
        post_status_on_pr(s3_data, deployment_status)
        
        put_job_success(job_id, 'Posted on the commit ')
    except Exception as e:
        # If any other exceptions which we didn't expect are raised
        # then fail the job and log the exception message.
        print('Function failed due to exception.')
        print(e)
        traceback.print_exc()
        put_job_failure(job_id, 'Function exception: ' + str(e))

    print('Function complete.')
    return "Complete."
    #     return {
    #     'statusCode': 200,
    #     'body': json.dumps('Hello from Lambda!')
    # }
    

