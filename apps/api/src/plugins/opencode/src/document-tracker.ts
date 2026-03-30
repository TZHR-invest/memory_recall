import type { ApiClient } from "./client";
import type { Config } from "./config";

export class DocumentTracker {
  private client: ApiClient;
  private config: Config;
  private directory: string;

  constructor(client: ApiClient, config: Config, directory: string) {
    this.client = client;
    this.config = config;
    this.directory = directory;
  }

  async scanAndMemorize(): Promise<number> {
    return 0;
  }

  async trackFile(_filePath: string): Promise<void> {}
}
