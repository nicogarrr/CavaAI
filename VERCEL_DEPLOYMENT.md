# Vercel Deployment Guide

This guide will help you deploy JLCavaAI to Vercel and configure all necessary environment variables.

## Prerequisites

1. A [Vercel](https://vercel.com) account
2. A [MongoDB Atlas](https://cloud.mongodb.com) account with a cluster
3. Required API keys (see below)

## Step 1: Prepare Your MongoDB Atlas Database

1. Go to [MongoDB Atlas](https://cloud.mongodb.com)
2. Create a new cluster (or use an existing one)
3. Navigate to **Network Access** in the left sidebar
4. Click **Add IP Address**
5. For Vercel deployments, add `0.0.0.0/0` to allow all IPs (Vercel uses dynamic IPs)
   - **Note**: For better security, you can use Vercel's IP ranges if available
6. Go to **Database Access** and create a database user with read/write permissions
7. Get your connection string:
   - Click **Connect** on your cluster
   - Choose **Connect your application**
   - Copy the connection string (format: `mongodb+srv://<username>:<password>@<cluster>.mongodb.net/<database>?retryWrites=true&w=majority`)
   - Replace `<password>` with your database user's password
   - Replace `<database>` with your database name (e.g., `cavaai`)

## Step 2: Generate Authentication Secret

Generate a secure authentication secret (32+ characters):

```bash
openssl rand -base64 32
```

Copy the output - you'll need this for `BETTER_AUTH_SECRET`.

## Step 3: Get API Keys

### Required:
- **MongoDB URI**: From Step 1
- **Better Auth Secret**: From Step 2

### Optional (Recommended):
- **Finnhub API Key**: [Register at Finnhub](https://finnhub.io/register) (free tier available)
- **Gemini API Key**: [Get from Google AI Studio](https://makersuite.google.com/app/apikey) (for AI features)

### Optional (Fallback Data Sources):
- **Twelve Data**: [Get API key](https://twelvedata.com/) (free: 8 calls/min)
- **Alpha Vantage**: [Get API key](https://www.alphavantage.co/support/#api-key) (free: 5 calls/min)
- **Polygon.io**: [Get API key](https://polygon.io/) (free tier available)
- **NewsAPI**: [Get API key](https://newsapi.org/) (free: 100 calls/day)
- **Marketaux**: [Get API key](https://www.marketaux.com/) (free: 100 calls/day)

### Optional (Email Features):
- **Gmail credentials**: For sending welcome emails
  - Use [App Passwords](https://support.google.com/accounts/answer/185833) if 2FA is enabled

## Step 4: Deploy to Vercel

### Option A: Deploy via Vercel Dashboard

1. Go to [Vercel Dashboard](https://vercel.com/dashboard)
2. Click **Add New** → **Project**
3. Import your GitHub repository
4. Vercel will auto-detect Next.js settings
5. Go to **Environment Variables** section
6. Add the following variables:

#### Required Variables:

```env
# Database
MONGODB_URI=mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/<db>?retryWrites=true&w=majority

# Authentication
BETTER_AUTH_SECRET=<your-generated-secret-from-step-2>
BETTER_AUTH_URL=https://your-app.vercel.app

# Node Environment
NODE_ENV=production
```

#### Recommended Variables:

```env
# Primary Data Source
FINNHUB_API_KEY=<your-finnhub-key>
FINNHUB_BASE_URL=https://finnhub.io/api/v1
```

#### Optional Variables:

```env
# AI Features
GEMINI_API_KEY=<your-gemini-key>

# Alternative Data Sources
TWELVE_DATA_API_KEY=<your-key>
ALPHA_VANTAGE_API_KEY=<your-key>
POLYGON_API_KEY=<your-key>
NEWSAPI_KEY=<your-key>
MARKETAUX_API_KEY=<your-key>

# Email
NODEMAILER_EMAIL=<your-email@gmail.com>
NODEMAILER_PASSWORD=<your-app-password>
```

7. Click **Deploy**

### Option B: Deploy via Vercel CLI

1. Install Vercel CLI:
```bash
npm i -g vercel
```

2. Login to Vercel:
```bash
vercel login
```

3. Deploy:
```bash
vercel
```

4. Follow the prompts and add environment variables when asked

## Step 5: Update BETTER_AUTH_URL

After your first deployment:

1. Note your Vercel deployment URL (e.g., `https://your-app.vercel.app`)
2. Go to your project settings in Vercel
3. Navigate to **Environment Variables**
4. Update `BETTER_AUTH_URL` to your actual deployment URL
5. Redeploy the application

## Step 6: Verify Deployment

1. Visit your deployed URL
2. Check the health endpoint: `https://your-app.vercel.app/api/health`
   - Should return `200` status with `"status": "healthy"`
   - If unhealthy, check which variables are missing
3. Try signing up for an account
4. Test the main features

## Troubleshooting

### 500 Internal Server Error

**Common causes:**

1. **Missing environment variables**
   - Check `/api/health` endpoint to see which variables are missing
   - Ensure `MONGODB_URI`, `BETTER_AUTH_SECRET`, and `BETTER_AUTH_URL` are set

2. **MongoDB connection issues**
   - Verify your MongoDB Atlas cluster is active
   - Check that `0.0.0.0/0` is in Network Access whitelist
   - Verify the connection string is correct (no spaces, correct password)
   - Make sure your database user has proper permissions

3. **Invalid BETTER_AUTH_SECRET**
   - Must be at least 32 characters
   - Cannot be default values like "your_better_auth_secret"
   - Regenerate with: `openssl rand -base64 32`

4. **Wrong BETTER_AUTH_URL**
   - Must match your deployment URL exactly
   - Should include `https://` prefix
   - No trailing slash

### Build Failures

1. Check build logs in Vercel dashboard
2. Ensure all dependencies are in `package.json`
3. TypeScript errors should be fixed before deployment

### MongoDB Connection Timeout

1. Allow 1-2 minutes for Network Access changes to propagate in MongoDB Atlas
2. Check if your cluster is paused (happens after inactivity on free tier)
3. Verify connection string format

## Security Notes

1. **Never commit** your `.env` file to git
2. Rotate your secrets regularly
3. In production, use specific IP whitelisting in MongoDB Atlas if possible
4. Use strong, unique passwords for your database users
5. Enable 2FA on your Vercel and MongoDB Atlas accounts

## Environment Variables Reference

See [.env.example](./.env.example) for a complete list of all environment variables with descriptions.

## Support

If you continue to have issues:

1. Check the health endpoint: `/api/health`
2. Review Vercel deployment logs
3. Check MongoDB Atlas logs
4. Open an issue on GitHub with:
   - Health check response
   - Relevant error messages (remove sensitive data)
   - Steps to reproduce

## Quick Checklist

Before deploying, ensure you have:

- [ ] MongoDB Atlas cluster created and running
- [ ] Network Access set to `0.0.0.0/0` in MongoDB Atlas
- [ ] Database user created with read/write permissions
- [ ] MongoDB connection string copied
- [ ] BETTER_AUTH_SECRET generated (32+ characters)
- [ ] Finnhub API key (optional but recommended)
- [ ] All environment variables added to Vercel
- [ ] BETTER_AUTH_URL set to your deployment URL
- [ ] Application deployed and health check passes

## Next Steps

After successful deployment:

1. Test user registration and login
2. Configure email settings (optional)
3. Set up monitoring and alerts
4. Configure custom domain (optional)
5. Set up automatic deployments from your git branch
