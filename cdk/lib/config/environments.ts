export interface LlmEvaluatorConfig {
  environment: string;

  vpcId: string;
  privateSubnetIds: string[];
  publicSubnetIds?: string[];
  certificateArn?: string;
  managedPrefixList?: string;

  cpu: number;
  memory: number;
  desiredCount: number;
}

// Placeholder per-environment config for this training repo. None of these
// IDs correspond to any real AWS account, VPC, subnet, certificate, or
// prefix list -- swap in real values (or use ec2.Vpc.fromLookup with a real
// account) before ever attempting `cdk deploy`.
export const environments: Record<string, LlmEvaluatorConfig> = {
  nonprod: {
    environment: "nonprod",
    vpcId: "vpc-00000000000000001",
    certificateArn: "11111111-1111-1111-1111-111111111111",
    managedPrefixList: "pl-00000000000000002",
    privateSubnetIds: ["subnet-00000000000000003", "subnet-00000000000000004"],
    publicSubnetIds: ["subnet-00000000000000005", "subnet-00000000000000006"],

    cpu: 512,
    memory: 1024,
    desiredCount: 1,
  },

  prod: {
    environment: "prod",
    vpcId: "vpc-00000000000000007",
    certificateArn: "22222222-2222-2222-2222-222222222222",
    managedPrefixList: "pl-00000000000000002",
    privateSubnetIds: ["subnet-00000000000000008", "subnet-00000000000000009"],
    publicSubnetIds: ["subnet-00000000000000010", "subnet-00000000000000011"],

    cpu: 1024,
    memory: 2048,
    desiredCount: 2,
  },
};
