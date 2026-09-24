import * as cdk from "aws-cdk-lib";
import * as ecs from "aws-cdk-lib/aws-ecs";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as ecr from "aws-cdk-lib/aws-ecr";
import * as ecs_patterns from "aws-cdk-lib/aws-ecs-patterns";
import * as acm from "aws-cdk-lib/aws-certificatemanager";
import * as route53 from "aws-cdk-lib/aws-route53";
import * as targets from "aws-cdk-lib/aws-route53-targets";
import * as cognito from "aws-cdk-lib/aws-cognito";
import * as elbv2 from "aws-cdk-lib/aws-elasticloadbalancingv2";
import * as iam from "aws-cdk-lib/aws-iam";
import * as s3 from "aws-cdk-lib/aws-s3";
import { Construct } from "constructs";
import { LlmEvaluatorConfig } from "./config/environments";

export interface LlmEvaluatorStackProps extends cdk.StackProps {
  config: LlmEvaluatorConfig;
}

export class LlmEvaluatorStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: LlmEvaluatorStackProps) {
    super(scope, id, props);
    const { config } = props;

    const environment       = this.node.tryGetContext("environment");
    const imageTag          = this.node.tryGetContext("imageTag");
    const ecrRepositoryName = this.node.tryGetContext("ecrRepositoryName");
    const ecsClusterName    = `llm-evaluator-${config.environment}`;
    const arnPrefix         = this.node.tryGetContext("arnPrefix");
    const litellmApiKey     = this.node.tryGetContext("litellmApiKey")  || "";
    const litellmApiBase    = this.node.tryGetContext("litellmApiBase") || "";
    const litellmModel      = this.node.tryGetContext("litellmModel")   || "claude-sonnet-4-6";
    const managedPrefixListId = this.node.tryGetContext("managedPrefixListId") || config.managedPrefixList;

    // NOTE: fictional internal domain -- replace with your own hosted zone
    // before deploying; this is a training/example stack.
    const domainName    = `llm-evaluator.aidev-${config.environment}.example.internal`;
    const hostedZoneName = `aidev-${config.environment}.example.internal`;

    /* -------------------- VPC -------------------- */
    const vpc = ec2.Vpc.fromLookup(this, "Vpc", { vpcId: config.vpcId });

    /* -------------------- COGNITO -------------------- */
    const userPool = new cognito.UserPool(this, "UserPool", {
      userPoolName: `llm-evaluator-${config.environment}`,
      selfSignUpEnabled: false,
      signInAliases: { username: true, email: true },
      standardAttributes: { email: { required: true, mutable: true } },
      passwordPolicy: {
        minLength: 8,
        requireLowercase: true,
        requireUppercase: true,
        requireDigits: true,
        requireSymbols: true,
      },
      accountRecovery: cognito.AccountRecovery.EMAIL_ONLY,
      removalPolicy: config.environment === "prod"
        ? cdk.RemovalPolicy.RETAIN
        : cdk.RemovalPolicy.DESTROY,
    });

    const userPoolClient = new cognito.UserPoolClient(this, "UserPoolClient", {
      userPool,
      userPoolClientName: `llm-evaluator-${config.environment}-alb`,
      generateSecret: true,
      oAuth: {
        flows: { authorizationCodeGrant: true },
        scopes: [
          cognito.OAuthScope.OPENID,
          cognito.OAuthScope.EMAIL,
          cognito.OAuthScope.PROFILE,
        ],
        callbackUrls: [`https://${domainName}/oauth2/idpresponse`],
        logoutUrls:   [`https://${domainName}`],
      },
      supportedIdentityProviders: [cognito.UserPoolClientIdentityProvider.COGNITO],
    });

    const userPoolDomain = new cognito.UserPoolDomain(this, "UserPoolDomain", {
      userPool,
      cognitoDomain: {
        domainPrefix: `llm-evaluator-${config.environment}-${this.account}`,
      },
    });

    /* -------------------- ECR -------------------- */
    const repo = ecr.Repository.fromRepositoryName(this, "Repo", ecrRepositoryName);

    /* -------------------- ECS CLUSTER -------------------- */
    const cluster = new ecs.Cluster(this, "Cluster", {
      vpc,
      clusterName: ecsClusterName,
    });

    /* -------------------- TASK DEFINITION -------------------- */
    const taskDef = new ecs.FargateTaskDefinition(this, "TaskDef", {
      cpu: config.cpu,
      memoryLimitMiB: config.memory,
    });

    taskDef.addContainer("AppContainer", {
      containerName: "llm-evaluator",
      image: ecs.ContainerImage.fromEcrRepository(repo, imageTag),
      logging: ecs.LogDriver.awsLogs({ streamPrefix: "llm-evaluator" }),
      portMappings: [{ containerPort: 5001 }],
      environment: {
        ENVIRONMENT:     environment,
        LITELLM_API_KEY: litellmApiKey,
        LITELLM_API_BASE: litellmApiBase,
        LITELLM_MODEL:   litellmModel,
      },
    });

    /* -------------------- ACM CERT -------------------- */
    const certificateArn = arnPrefix + ":certificate/" + config.certificateArn;
    const certificate = acm.Certificate.fromCertificateArn(this, "Certificate", certificateArn);

    /* -------------------- FARGATE SERVICE + ALB -------------------- */
    const service = new ecs_patterns.ApplicationLoadBalancedFargateService(
      this,
      "Service",
      {
        cluster,
        taskDefinition: taskDef,
        desiredCount: config.desiredCount,
        publicLoadBalancer: true,
        listenerPort: 443,
        protocol: cdk.aws_elasticloadbalancingv2.ApplicationProtocol.HTTPS,
        certificate,
        openListener: false,
        redirectHTTP: true,
      }
    );

    const lb = service.loadBalancer;

    /* -------------------- LISTENER RULES -------------------- */
    // /healthz — no auth (required for ALB target group health checks)
    service.listener.addAction("HealthCheck", {
      priority: 1,
      conditions: [elbv2.ListenerCondition.pathPatterns(["/healthz"])],
      action: elbv2.ListenerAction.forward([service.targetGroup]),
    });

    // Default: Cognito authentication for everything else
    const cfnListener = service.listener.node.defaultChild as elbv2.CfnListener;
    cfnListener.defaultActions = [
      {
        type: "authenticate-cognito",
        authenticateCognitoConfig: {
          userPoolArn:      userPool.userPoolArn,
          userPoolClientId: userPoolClient.userPoolClientId,
          userPoolDomain:   userPoolDomain.domainName,
          onUnauthenticatedRequest: "authenticate",
          scope: "openid email profile",
          sessionTimeout: "604800",
        },
        order: 1,
      },
      {
        type: "forward",
        forwardConfig: {
          targetGroups: [{ targetGroupArn: service.targetGroup.targetGroupArn, weight: 1 }],
        },
        order: 2,
      },
    ];

    /* -------------------- ALB ACCESS LOGS -------------------- */
    const albLogsBucket = new s3.Bucket(this, "AlbLogsBucket", {
      bucketName: `llm-evaluator-alb-logs-${config.environment}-${this.account}`,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      encryption: s3.BucketEncryption.S3_MANAGED,
    });
    lb.logAccessLogs(albLogsBucket);

    /* -------------------- SECURITY GROUP / INGRESS -------------------- */
    if (managedPrefixListId) {
      lb.connections.allowFrom(
        ec2.Peer.prefixList(managedPrefixListId),
        ec2.Port.tcp(443),
        "Allow intranet access via managed prefix list"
      );
    }

    lb.connections.allowFrom(
      ec2.Peer.ipv4(vpc.vpcCidrBlock),
      ec2.Port.tcp(443),
      "Allow internal VPC services"
    );

    lb.connections.allowTo(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(443),
      "Allow ALB to call Cognito for token exchange"
    );

    /* -------------------- HEALTH CHECK -------------------- */
    service.targetGroup.configureHealthCheck({
      path: "/healthz",
      healthyHttpCodes: "200",
      interval: cdk.Duration.seconds(30),
      timeout: cdk.Duration.seconds(5),
      healthyThresholdCount: 2,
      unhealthyThresholdCount: 3,
    });

    /* -------------------- DNS -------------------- */
    const hostedZone = route53.HostedZone.fromLookup(this, "HostedZone", { domainName: hostedZoneName });

    new route53.ARecord(this, "DnsRecord", {
      zone: hostedZone,
      recordName: "llm-evaluator",
      target: route53.RecordTarget.fromAlias(new targets.LoadBalancerTarget(lb)),
    });

    /* -------------------- OUTPUTS -------------------- */
    new cdk.CfnOutput(this, "AppUrl", {
      value: `https://${domainName}`,
      description: "LLM Evaluator URL",
    });
    new cdk.CfnOutput(this, "LoadBalancerDNS", {
      value: lb.loadBalancerDnsName,
      description: "Load Balancer DNS name",
    });
  }
}
