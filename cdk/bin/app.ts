#!/usr/bin/env node
import "source-map-support/register";
import * as cdk from "aws-cdk-lib";
import { LlmEvaluatorStack } from "../lib/llm_evaluator_stack";
import { environments } from "../lib/config/environments";

const app = new cdk.App();

const account =
  process.env.CDK_DEFAULT_ACCOUNT ||
  process.env.AWS_ACCOUNT_ID;

const region =
  process.env.CDK_DEFAULT_REGION ||
  process.env.AWS_DEFAULT_REGION ||
  "us-east-1";

if (!account) {
  throw new Error(
    "❌ No AWS account found. Set CDK_DEFAULT_ACCOUNT or AWS_ACCOUNT_ID."
  );
}

const envName = app.node.tryGetContext("environment") || "nonprod";
const config = environments[envName];

if (!config) {
  throw new Error(`Environment '${envName}' not found in environments.ts`);
}

new LlmEvaluatorStack(app, `LlmEvaluatorStack-${envName}`, {
  config,
  env: { account, region },
});
