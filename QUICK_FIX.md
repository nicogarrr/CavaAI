# Quick Fix for 500 Internal Server Error

## The Problem

The application at https://cavaai.vercel.app/ is showing a **500 Internal Server Error** because required environment variables are not configured in Vercel.

## The Solution (5 Minutes)

### Step 1: Check Current Status

Visit: https://cavaai.vercel.app/api/health

This will show you which environment variables are missing.

### Step 2: Configure Required Environment Variables in Vercel

1. Go to your [Vercel Project Dashboard](https://vercel.com/dashboard)
2. Select your project (CavaAI)
3. Go to **Settings** → **Environment Variables**
4. Add the following **required** variables:

#### Minimum Required Configuration:

```env
MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/database?retryWrites=true&w=majority
BETTER_AUTH_SECRET=<generate with: openssl rand -base64 32>
BETTER_AUTH_URL=https://cavaai.vercel.app
NODE_ENV=production
```

### Step 3: Get Your MongoDB URI

If you don't have MongoDB Atlas set up yet:

1. Go to [MongoDB Atlas](https://cloud.mongodb.com)
2. Create a free cluster (if you don't have one)
3. Go to **Network Access** → **Add IP Address** → Add `0.0.0.0/0`
4. Go to **Database Access** → **Add New Database User**
   - Create a user with password
   - Grant "Read and write to any database" permission
5. Click **Connect** on your cluster
6. Choose **Connect your application**
7. Copy the connection string and replace:
   - `<username>` with your database username
   - `<password>` with your database password
   - `<database>` with a database name (e.g., `cavaai`)

### Step 4: Generate Authentication Secret

Run this command in your terminal:

```bash
openssl rand -base64 32
```

Copy the output and use it as your `BETTER_AUTH_SECRET`.

### Step 5: Add Variables to Vercel

In Vercel Environment Variables:

| Variable Name         | Value                                    | Environment          |
|-----------------------|------------------------------------------|----------------------|
| `MONGODB_URI`         | Your MongoDB connection string           | Production, Preview  |
| `BETTER_AUTH_SECRET`  | Your generated secret (32+ chars)        | Production, Preview  |
| `BETTER_AUTH_URL`     | `https://cavaai.vercel.app`              | Production           |
| `NODE_ENV`            | `production`                             | Production           |

### Step 6: Redeploy

1. In Vercel Dashboard, go to **Deployments**
2. Click on the latest deployment
3. Click **Redeploy** (or push a new commit to trigger deployment)

### Step 7: Verify

1. Wait for deployment to complete (~2 minutes)
2. Visit https://cavaai.vercel.app/api/health
   - Should return: `{"status": "healthy", ...}`
3. Visit https://cavaai.vercel.app
   - Should load without 500 error

## Optional But Recommended

Add these for better functionality:

```env
# Market Data (Free)
FINNHUB_API_KEY=<get from https://finnhub.io/register>
FINNHUB_BASE_URL=https://finnhub.io/api/v1

# AI Features (Free with limits)
GEMINI_API_KEY=<get from https://makersuite.google.com/app/apikey>
```

## Common Issues

### Still Getting 500 Error After Setup?

1. **Wait 1-2 minutes** after adding IP to MongoDB Atlas Network Access
2. **Check the health endpoint** to see specific errors: `/api/health`
3. **Verify MongoDB connection string**:
   - No extra spaces
   - Password is correctly encoded (use URL encoding for special chars)
   - Database name is included
4. **Verify BETTER_AUTH_SECRET**:
   - Must be at least 32 characters
   - Cannot be default values like "your_better_auth_secret"
5. **Check Vercel logs**:
   - Go to Deployments → Latest deployment → Build logs
   - Look for specific error messages

### MongoDB Connection Fails?

- Ensure MongoDB Atlas cluster is not paused (free tier pauses after 60 days of inactivity)
- Double-check Network Access settings allow `0.0.0.0/0`
- Verify database user has correct permissions
- Test connection string in MongoDB Compass or similar tool

### Authentication Errors?

- Make sure `BETTER_AUTH_URL` matches your actual deployment URL
- Verify `BETTER_AUTH_SECRET` is properly set and is 32+ characters
- Clear cookies and try again

## Need More Help?

- **Full deployment guide**: See [VERCEL_DEPLOYMENT.md](./VERCEL_DEPLOYMENT.md)
- **All environment variables**: See [.env.example](./.env.example)
- **Health check**: Visit `/api/health` on your deployment
- **Open an issue**: [GitHub Issues](https://github.com/nicogarrr/CavaAI/issues)

## Security Note

⚠️ **NEVER** commit actual secrets to your repository. Only commit `.env.example` with placeholder values.
