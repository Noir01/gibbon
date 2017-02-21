{-# LANGUAGE OverloadedStrings #-}
{-# OPTIONS_GHC -fno-warn-name-shadowing #-}

{-# LANGUAGE BangPatterns #-}
{-# LANGUAGE ScopedTypeVariables #-}

module Packed.FirstOrder.Passes.Typecheck
    ( typecheckStrict
    , typecheckPermissive
    , typecheck
--    , typecheckExp
    , TCConfig(..)
    ) where

import Prelude hiding (fail)
import Packed.FirstOrder.Common
import Packed.FirstOrder.L2_Traverse as L2
import qualified Packed.FirstOrder.L1_Source as L1

import qualified Data.Map as M
import qualified Data.List as L
import qualified Data.Set as S
import Control.Monad.ST
import Control.Monad
import Data.STRef

lvl :: Int
lvl = 1

data TCVar s = Concrete L1.Ty
             | Fun L1.Ty L1.Ty
             | Alias (STRef s (Either (TCVar s) ()))
               -- ^ Left signifies a constraint and Right signifies a
               -- free, unconstrained var.

instance Show (TCVar s) where
  show (Concrete t) = "Concrete "++show t
  show (Fun a b) = "Fun "++show a++" "++show b
  show (Alias _) = "Alias"

data TCConfig =
    TCConfig
    { postCursorize :: Bool -- ^ The type of certain operations change after Cursorize.
    , checkCursors  :: Bool -- ^ WIP: typecheck cursors (MV)
    }

type TCEnv s = M.Map Var (TCVar s)

--------------------------------------------------------------------------------

-- | Entrypoint with the expected type for a pass in the top-level compiler pipeline.
typecheckStrict :: TCConfig -> L2.Prog -> SyM L2.Prog
typecheckStrict cfg prg = if typecheck True cfg prg
                          then return prg
                          else error "Compiler exiting due to above type errors."
-- WARNING: depending on DEBUG, "above type errors" may not actually show.
-- !!TODO!!: switch to a writer monad to accumulate error messages, rather than dbgTrace.

-- | In contrast with 'typecheckStrict', this issues type errors only as warnings.
typecheckPermissive :: TCConfig -> L2.Prog -> SyM L2.Prog
typecheckPermissive cfg prg = do let !_ = typecheck False cfg prg
                                 return prg


-- | Run typecheck and report errors using the trace mechanism.
-- Returns true if the program typechecks.
typecheck :: Bool -> TCConfig -> L2.Prog -> Bool
typecheck strict cfg prg = runST $ do
                  rf <- newSTRef True
                  !_ <- typecheck' cfg rf prg
                  b <- readSTRef rf
                  if b then
                     (if strict
                      then return b
                      else dbgTrace lvl " [typecheck] Succeeded!\n" (return b))
                    else
                     dbgTrace lvl " [typecheck] Found failures above!\n"
                     (return b)


-- | Entrypoint for typechecking just an expression:
typecheckExp :: DDefs L1.Ty -> L1.Exp -> L1.Ty
typecheckExp =
    -- Reusing code here is tricky... we could wrap it up in a dummy
    -- Prog, but that requires having a Main type already.
    error "typecheckExp FINISHME"

typecheck' :: forall s . TCConfig -> STRef s Bool -> L2.Prog -> ST s L2.Prog
typecheck' TCConfig{postCursorize,checkCursors} success prg@(L2.Prog defs _funs _main) = eachFn fn prg
 where
  eachFn fn (Prog dd fundefs mainExp) =
      do let funEnv = fEnv $ includeBuiltins $ progToEnv (Prog dd fundefs mainExp)
         newFunDefs <- forM fundefs $ \(L2.FunDef nm arrTy@(ArrowTy inT _ outT) arg bod) -> do
                         let env = Env2 (M.singleton arg (fmap (\_->()) inT)) funEnv
                         mty <- fn env (Just arg) bod
                         case mty of
                           Nothing -> reportErr $ "Typecheck of function " ++ (fromVar nm) ++ " failed."
                           Just ty -> if ty == (fmap (\_->()) outT)
                                      then return ()
                                      else reportErr $ "In function " ++ (fromVar nm) ++
                                               ", expected return type " ++ (show outT) ++
                                               " and got return type " ++ (show ty) ++ "."
                         return $ L2.FunDef nm arrTy arg bod
         newMainExpr <- forM mainExp $ \(e,t) -> do
                          mty <- fn (Env2 M.empty funEnv) Nothing e
                          case mty of
                            Nothing -> reportErr $ "Typecheck of main expr failed"
                            Just _ty -> return ()
                          return (e,t)
         return $ Prog dd newFunDefs newMainExpr

  fn Env2{vEnv,fEnv} args exp0 =
      do let initTCE = M.map Concrete vEnv `M.union`
                       M.map (\(a,b) -> Fun a b) fEnv
         tv <- tE defs initTCE exp0
         mty <- extractTCVar tv
         let args' = case args of
                       Nothing -> []
                       Just v  -> [v]
         if checkCursors -- do special check if flag is set
         then do if tECur defs [(S.fromList args')] exp0 then return mty 
                 else return Nothing -- TODO: do something smarter if cursor check fails
         else return mty

  -- | This uses the "success" flag from above.
  tE :: DDefs L1.Ty -> TCEnv s -> Exp -> ST s (TCVar s)
  tE dd tcenv ex0 =
      let go = tE dd tcenv in -- Simple recursion where we don't change the env.
      case ex0 of
        VarE v  -> lookupTCVar tcenv v
        LitE _i -> return $ Concrete IntTy
        AppE v e ->
            do te <- go e
               let fty = M.lookup v tcenv
               case fty of
                 Nothing -> failFresh $ "Couldn't look up type of function: " ++ (show v)
                 Just (Fun a b) -> do assertEqTCVar ex0 (Concrete a) te
                                      return (Concrete b)
                 Just oth -> failFresh $ "Function had non-arrow type: " ++ show oth

-- FIXME: This is redundant with primRetTy primArgsTy helper functions:
        PrimAppE p es ->
            do tes <- mapM (go) es
               case p of
                 L1.AddP -> do mapM_ (assertEqTCVar ex0 (Concrete IntTy)) tes
                               return $ Concrete IntTy
                 L1.SubP -> do mapM_ (assertEqTCVar ex0 (Concrete IntTy)) tes
                               return $ Concrete IntTy
                 L1.MulP -> do mapM_ (assertEqTCVar ex0 (Concrete IntTy)) tes
                               return $ Concrete IntTy
                 L1.EqIntP -> do mapM_ (assertEqTCVar ex0 (Concrete IntTy)) tes
                                 return $ Concrete BoolTy
                 L1.EqSymP -> do mapM_ (assertEqTCVar ex0 (Concrete SymTy)) tes
                                 return $ Concrete BoolTy

                 -- Polymorphic!:
                 L1.ErrorP _s t   -> return $ Concrete t
                 L1.DictEmptyP t  -> return $ Concrete $ SymDictTy t

                 -- Only dict lookup on SYMBOL keys for now:
                 L1.DictLookupP t
                    | [d,k] <- tes -> do assertEqTCVar ex0 (Concrete (SymDictTy t)) d
                                         assertEqTCVar ex0 (Concrete SymTy) k
                                         return $ Concrete t
                    | otherwise -> failFresh$ "wrong number of arguments to DictLookupP: "++ndoc es
                 L1.DictInsertP t
                    | [d,k,v] <- tes -> do assertEqTCVar ex0 (Concrete (SymDictTy t)) d
                                           assertEqTCVar ex0 (Concrete SymTy) k
                                           assertEqTCVar ex0 (Concrete t) v
                                           return $ Concrete (SymDictTy t)
                    | otherwise -> failFresh$ "wrong number of arguments to DictInsertP: "++ndoc es

                 L1.SizeParam -> return $ Concrete IntTy
                 L1.MkTrue    -> return $ Concrete BoolTy
                 L1.MkFalse   -> return $ Concrete BoolTy

                 L1.MkNullCursor -> return $ Concrete (CursorTy ())
                 -- WARNING: tricky convention here.  We DONT update 'ty' to CursorTy, because we need to remember
                 -- the name of this type for later (i.e. calling the right print function).
                 L1.ReadPackedFile _ _ ty -> return $ Concrete ty

                 -- _ -> failFresh $ "Case not handled in typecheck: " ++ (show p)

        LetE (v,t,e') e ->
            do te' <- go e'
               assertEqTCVar ex0 (Concrete t) te'
               tE dd (M.insert v (Concrete t) tcenv) e
        IfE e1 e2 e3 ->
            do te1 <- go e1
               te2 <- go e2
               te3 <- go e3
               assertEqTCVar ex0 (Concrete BoolTy) te1
               assertEqTCVar ex0 te2 te3
               return te2
        ProjE i e ->
            do te <- go e
               checkProd te i e
        MkProdE es ->
            do tes <- mapM (go) es
               outty <- allConcrete tes es
               case outty of
                 Nothing -> failFresh "Giving up on typing MkProdE"
                 Just outty' ->
                     return $ Concrete outty'
        CaseE e cs
            | postCursorize -> do te <- go e
                                  assertEqTCVar ex0 (Concrete (CursorTy ())) te
                                  typecheckCasesPostCursorize cs
            | otherwise -> do te <- go e
                              let tycons = L.map (getTyOfDataCon dd . fst3) cs
                              case L.nub tycons of
                                [one] -> do assertEqTCVar ex0 (Concrete (PackedTy one ())) te
                                            typecheckCases cs
                                oth -> failFresh $ "case branches have mismatched types, "
                                         ++ndoc oth++", in "++ndoc ex0

        MkPackedE c es
            --  After cursorize, these become single argument; take and return cursors.
            | postCursorize -> case es of
                                 [curs] -> do cty <- go curs
                                              assertEqTCVar ex0 (Concrete (CursorTy ())) cty
                                              return (Concrete (CursorTy ()))
                                 _ -> failFresh $ "MkPackedE "++c++" expected one argument, got: "++ndoc es
            | otherwise -> do tes <- mapM (go) es
                              let te = Concrete $ L1.Packed $ getTyOfDataCon dd c
                                  args = lookupDataCon dd c
                              if length tes /= length args
                               then reportErr $ "wrong number of arguments to constructor "
                                      ++show c++": "++show (length tes)
                               else sequence_ [ assertEqTCVar ex0 (Concrete expect) actual
                                              | (expect,actual) <- zip args tes ]
                              return te

        TimeIt e t _b ->
            do te <- go e
               assertEqTCVar ex0 (Concrete t) te
               return te
        _ -> failFresh $ "Case not handled in typecheckExp: " ++ (show ex0)
   where

    checkProd te i e =
      let fail = failFresh $ "In checking " ++ (show e) ++
                  ", I expected a product type, but found " ++ (show te) ++ "." in
      case te of
        Concrete (ProdTy ts) -> return $ Concrete $ ts !! i
        Alias r -> do r' <- readSTRef r
                      case r' of
                        Left tcv -> checkProd tcv i e
                        Right () -> failFresh $ "I ran into a ProjE of " ++ (show e) ++
                                            ", but I don't know the type of that thing."
        Concrete _ -> fail
        Fun _ _    -> fail


    allConcrete [] _ = return $ Just $ ProdTy [] -- Unit type.
    allConcrete ((Concrete t1):t2:ts) es = do pts <- allConcrete (t2:ts) es
                                              case pts of
                                                Nothing -> return Nothing
                                                Just (ProdTy ts') ->
                                                    return $ Just $ ProdTy $ t1:ts'
                                                Just _ -> error "impossible."

    -- We don't allow singleton tuples in general, but here we plan to
    -- recursively build up the product types.
    allConcrete [(Concrete t)] _es = return $ Just $ ProdTy [t]
    allConcrete _ es = do reportErr $ "Tried to do a MkProdE of " ++ (show es) ++
                                      " but couldn't determine its type."
                          return Nothing

    -- | In the postCursorize world, CaseE takes a cursor and each
    -- branch receives a cursor argument.
    typecheckCasesPostCursorize cs = do
      let go acc []      = return acc
          go acc ((dcon,ls,rhs):rst) =
              case ls of
                [curV] -> do rty <- tE dd (M.insert curV (Concrete (CursorTy ())) tcenv) rhs
                             assertEqTCVar ex0 acc rty
                             go acc rst
                _ -> do acc' <- failFresh $ "expected one pattern var in post-cursorize case branch: "++ndoc (dcon,ls,rhs)
                        go acc' rst
      acc0 <- freshTCVar
      go acc0 cs

    typecheckCases cs =
        do tcs <- forM cs $ \(c,args,e) ->
                  do let targs = map Concrete $ lookupDataCon dd c
                         ntcenv = M.fromList (zip args targs) `M.union` tcenv
                     tE dd ntcenv e
           -- Make sure all braches unify:
           foldM_ (\i a -> (assertEqTCVar ex0 i a) >> (return a)) (head tcs) (tail tcs)
           return $ head tcs

  --  Simple function to check cursors
  --  (Could be merged with tE, not sure if making a separate function is the right approach.)
  tECur :: DDefs L1.Ty -> [S.Set Var] -> Exp -> Bool
  tECur dd obl ex0 =
      -- check that all obligations are met in ex0
      case ex0 of
        
        -- when we hit a tail call we check if obl is empty
        VarE _v ->
            check obl
        LitE _i ->
            check obl
        AppE _v _e ->
            check obl
        PrimAppE _p _es ->
            check obl
        ProjE _i _e ->
            check obl
        MkProdE _es ->
            check obl
        MkPackedE _c _es ->
            check obl
        TimeIt e _t _b ->
            tECur dd obl e

        -- otherwise see if a binding met an obligation
        LetE (v,_t,e') e ->
            case fromEndVar v of
              Nothing -> handleLet e' e
              Just v' -> if varPresent v' obl
                         -- don't need to recur on rhs? should be flattened
                         then let obl' = removeVar v' obl
                              in tECur dd obl' e
                         else handleLet e' e
        IfE _e1 e2 e3 ->
            -- both the then and else of the if need to be checked
            (tECur dd obl e2) && (tECur dd obl e3)
        CaseE (VarE v) cs ->
            if varPresent v obl
            -- TODO: matching should introduce alias for matched variable
            -- TODO: introduce obligations for variables in each case in cs
            then undefined
            else undefined
                 
        _ -> dbgTrace lvl (" [typecheck] Failed to match in tECur on " ++ (show ex0)) False
      where
        handleLet (AppE f (MkProdE [VarE v,_])) e =
            if ((fromVar f) == "AddCursor")
            then if varPresent v obl
                 then tECur dd (removeVar v obl) e
                 else dbgTrace lvl (" [typecheck] AddCursor I don't understand: " ++ (show v)) $ tECur dd obl e
            else tECur dd obl e
        handleLet (AppE f e') e = undefined -- TODO: handle recursive calls, etc
        handleLet _ e = tECur dd obl e
        check obl =
            if L.null obl then True
            else dbgTrace lvl (" [typecheck] Failed to meet obligations: " ++ (show obl)) False


  -- TODO: implement these functions
                 
  varPresent :: Var -> [S.Set Var] -> Bool
  varPresent = undefined

  removeVar :: Var -> [S.Set Var] -> [S.Set Var]
  removeVar = undefined

  --  This is not top-level because it is under the scope of 'success':
  reportErr :: String -> ST s ()
  reportErr str = do
    writeSTRef success False
    return $! dbgTrace lvl (" [typecheck] " ++ str) ()

  failFresh :: String -> ST s (TCVar s)
  failFresh str = do reportErr str
                     freshTCVar

  freshTCVar :: ST s (TCVar s)
  freshTCVar = do
    r <- newSTRef $ Right ()
    return $ Alias r

  lookupTCVar :: TCEnv s -> Var -> ST s (TCVar s)
  lookupTCVar tcenv v =
      case M.lookup v tcenv of
        Nothing
                -- FIXME: Go stricter and remove this exception:
                | isEndVar v -> return (Concrete (CursorTy ()))
                                -- Policy: do we allow unbound end-witnesses?  They may not really be used.
                | otherwise  -> do reportErr $ "Failed to look up type of var " ++ (show v)
                                   freshTCVar
        Just tcv -> return tcv

  assertEqTCVar :: Exp -> TCVar s -> TCVar s -> ST s ()
  assertEqTCVar e (Concrete t1) (Concrete t2) =
      if t1 == t2
      then return ()
      else reportErr $ "Types not equal: " ++ (ndoc t1) ++ ", " ++ (ndoc t2)
                      ++ "\n  (when checking expression " ++ abbrv 80 e ++")"
  assertEqTCVar e (Concrete t) (Alias a) = makeEqTCVar t a e
  assertEqTCVar e (Alias a) (Concrete t) = makeEqTCVar t a e
  assertEqTCVar e (Alias a1) (Alias a2) = makeEqAlias a1 a2 e

-- FIXME: finish fun type handling:
--  assertEqTCVar e (Fun a b) (Fun c d) =

  makeEqTCVar :: L1.Ty -> STRef s (Either (TCVar s) ()) -> Exp -> ST s ()
  makeEqTCVar t r e =
      do r' <- readSTRef r
         case r' of
           Left tcv -> assertEqTCVar e tcv (Concrete t)
           Right () -> writeSTRef r $ Left $ Concrete t

  makeEqAlias :: STRef s (Either (TCVar s) ()) -> STRef s (Either (TCVar s) ()) -> Exp -> ST s ()
  makeEqAlias r1 r2 e =
      do r1' <- readSTRef r1
         r2' <- readSTRef r2
         case (r1',r2') of
              (Right (), Right ()) ->
                  do tv <- freshTCVar
                     writeSTRef r1 $ Left tv
                     writeSTRef r2 $ Left tv
              (Left tcv, Right ()) -> writeSTRef r2 $ Left tcv
              (Right (), Left tcv) -> writeSTRef r1 $ Left tcv
              (Left tc1, Left tc2) -> assertEqTCVar e tc1 tc2

  extractTCVar :: (TCVar s) -> ST s (Maybe L1.Ty)
  extractTCVar (Concrete t) = return (Just t)
  extractTCVar (Alias r) =
      do r' <- readSTRef r
         case r' of
           Left tcv -> extractTCVar tcv
           Right () -> do reportErr "Expression didn't have a type that I could figure out"
                          return Nothing

fst3 :: forall t t1 t2. (t, t1, t2) -> t
fst3 (a,_,_) = a
